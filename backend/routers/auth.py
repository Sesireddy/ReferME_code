"""Auth endpoints — Phase C refactor.

URLs and behaviour preserved. All shared helpers + Pydantic models are imported
from `server.py` (which continues to own the bcrypt/JWT/OTP/email plumbing so
existing tests and other routers keep working unchanged).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from server import (
    db,
    current_user,
    require_role,
    hash_password,
    verify_password,
    create_jwt,
    push_notification,
    now_iso,
    now_ts,
    new_id,
    make_referral_code,
    is_student_complete,
    student_missing_fields,
    student_profile_completion,
    send_otp_email,
    send_otp_sms_msg91,
    user_public,
    compute_pro_profile_completion,
    pro_missing_fields,
    normalize_indian_mobile,
    PERSONAL_EMAIL_DOMAINS,
    FREE_TIER_ACTIONS,
    REFERRAL_REWARD,
    MOCK_OTP_MODE,
    MOCK_SMS_MODE,
    TEST_RETURN_OTP,
    EMERGENT_AUTH_URL,
    SignupBody,
    VerifyOtpBody,
    LoginBody,
    ForgotBody,
    ResetBody,
    GoogleSessionBody,
    PhoneOtpSendBody,
    PhoneOtpVerifyBody,
    GmailVerifyBody,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------- Signup + Email OTP -------------------
@router.post("/auth/signup")
async def signup(body: SignupBody):
    if body.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot self-register as admin")
    if body.role == "employer":
        raise HTTPException(
            status_code=400,
            detail="For employer assistance, please contact our team at Team@referme.today",
        )
    email_lower = body.email.lower().strip()
    domain = email_lower.split("@")[-1] if "@" in email_lower else ""
    if body.role == "professional" and domain in PERSONAL_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Use your company email (not {domain}). Personal email domains are not allowed for Working Professionals.",
        )
    existing = await db.users.find_one({"email": email_lower}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # ---------- Referral anti-fraud ----------
    # Iteration 57: Referrals now apply to ALL roles (students + working professionals).
    # The referral stays `pending` until the referred user's first successful deposit.
    referrer_user = None
    ref_code_raw = (body.ref or "").strip().upper()
    if ref_code_raw:
        referrer_user = await db.users.find_one({"referral_code": ref_code_raw}, {"_id": 0})
        if not referrer_user:
            raise HTTPException(status_code=400, detail="Invalid referral code. Please check and try again.")
        if referrer_user.get("account_status") and referrer_user["account_status"] != "active":
            raise HTTPException(status_code=400, detail="Invalid referral code. Please check and try again.")
        if referrer_user.get("email", "").lower() == email_lower:
            referrer_user = None

    user_doc = {
        "id": new_id(),
        "email": email_lower,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "name": body.name or "",
        "is_email_verified": False,
        "account_status": "active",
        "credits": 100 if body.role == "student" else 0,
        "free_uses_left": 0 if body.role == "student" else (FREE_TIER_ACTIONS * 2),
        "total_deposits": 0,
        "profile_complete": False,
        "profile": {},
        "referral_code": make_referral_code(),
        "referred_by": referrer_user["id"] if referrer_user else None,
        "created_at": now_iso(),
    }
    while await db.users.find_one({"referral_code": user_doc["referral_code"]}, {"_id": 0}):
        user_doc["referral_code"] = make_referral_code()
    await db.users.insert_one(user_doc)

    if referrer_user:
        await db.referrals.insert_one({
            "id": new_id(),
            "referrer_id": referrer_user["id"],
            "referrer_role": referrer_user.get("role"),
            "referred_id": user_doc["id"],
            "referred_role": body.role,
            "referred_email": email_lower,
            "code": ref_code_raw,
            "status": "pending",  # pending → qualified → rewarded (or rejected)
            "reward_credits": REFERRAL_REWARD,
            "wallet_deposit_status": "pending",  # flips to 'completed' on first successful deposit
            "qualified_at": None,
            "rewarded_at": None,
            "created_at": now_iso(),
            "completed_at": None,
        })
    if body.role == "student":
        await db.transactions.insert_one({
            "id": new_id(),
            "user_id": user_doc["id"],
            "delta": 100,
            "reason": "signup_bonus",
            "meta": {"label": "Signup Bonus - 100 Credits"},
            "created_at": now_iso(),
        })
    otp_code = f"{secrets.randbelow(10**6):06d}"
    await db.otps.insert_one({
        "id": new_id(),
        "email": email_lower,
        "otp_hash": hash_password(otp_code),
        "purpose": "verify_email",
        "expires_at": now_ts() + 600,
        "consumed": False,
        "created_at": now_iso(),
    })
    sent = await send_otp_email(email_lower, otp_code, "verify_email")
    resp = {"message": "Signup successful. OTP sent.", "email": email_lower, "email_sent": bool(sent)}
    if MOCK_OTP_MODE or not sent or TEST_RETURN_OTP:
        resp["mock_otp"] = otp_code
    return resp


@router.post("/auth/verify-otp")
async def verify_otp(body: VerifyOtpBody):
    otp_doc = await db.otps.find_one(
        {
            "email": body.email.lower(),
            "purpose": body.purpose,
            "consumed": False,
            "expires_at": {"$gt": now_ts()},
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not otp_doc:
        raise HTTPException(status_code=400, detail="OTP invalid or expired")
    if not verify_password(body.otp, otp_doc["otp_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect OTP")
    await db.otps.update_one({"id": otp_doc["id"]}, {"$set": {"consumed": True}})
    if body.purpose == "verify_email":
        existing = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
        was_unverified = bool(existing and not existing.get("is_email_verified"))
        u = await db.users.find_one_and_update(
            {"email": body.email.lower()},
            {"$set": {"is_email_verified": True}},
            return_document=True,
            projection={"_id": 0},
        )
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        token = create_jwt(u["id"], u["role"])
        await push_notification(u["id"], "Welcome to ReferME 🎉", "Your email has been verified.", "success")
        welcome_bonus = 0
        if was_unverified and u["role"] == "student":
            welcome_bonus = 100
            await push_notification(
                u["id"],
                "Signup Bonus Credited 🎁",
                "100 Credits have been added to your wallet as a welcome bonus.",
                "success",
            )
        # Referral policy (Iteration 57): Do NOT credit the referrer on email-verification.
        # The referral stays `pending` until the referred user makes their first successful
        # wallet deposit (see wallet.py confirm_deposit). Only notify the referrer here.
        if was_unverified:
            pending = await db.referrals.find_one(
                {"referred_id": u["id"], "status": "pending"}, {"_id": 0}
            )
            if pending:
                referrer = await db.users.find_one({"id": pending["referrer_id"]}, {"_id": 0})
                if referrer and referrer.get("email", "").lower() == u.get("email", "").lower():
                    # Self-referral guard — mark rejected so it never rewards
                    await db.referrals.update_one(
                        {"id": pending["id"]},
                        {"$set": {"status": "rejected", "reason": "self_referral", "completed_at": now_iso()}},
                    )
                elif referrer:
                    await push_notification(
                        referrer["id"],
                        "New referral signed up 🌟",
                        f"{u.get('name') or 'A new user'} has successfully signed up using your referral. Referral reward will be credited after their first successful wallet deposit.",
                        "info",
                    )
        return {"token": token, "user": user_public(u), "welcome_bonus": welcome_bonus}
    return {"message": "OTP verified", "reset_token": body.otp}


# ------------------- Phone (SMS) OTP — MOCK MODE -------------------
@router.post("/profile/phone/send-otp")
async def phone_send_otp(body: PhoneOtpSendBody, u: dict = Depends(current_user)):
    phone_e164, err = normalize_indian_mobile(body.phone or "")
    if err:
        raise HTTPException(status_code=400, detail=err)
    phone = phone_e164
    otp_code = f"{secrets.randbelow(10**6):06d}"
    await db.otps.insert_one({
        "id": new_id(),
        "user_id": u["id"],
        "phone": phone,
        "otp_hash": hash_password(otp_code),
        "purpose": "verify_phone",
        "expires_at": now_ts() + 600,
        "consumed": False,
        "created_at": now_iso(),
    })
    # Try MSG91 SMS first. On failure, fall back to mock-log so signup flows
    # in dev/CI keep working (they can still read `mock_otp` when TEST_RETURN_OTP=1).
    sent, provider_msg = await send_otp_sms_msg91(phone, otp_code)
    resp: dict = {"phone": phone}
    if sent:
        resp["message"] = "OTP sent via SMS"
        resp["provider"] = "msg91"
    else:
        resp["message"] = "Mock SMS sent" if MOCK_SMS_MODE else "SMS provider failed — mock fallback"
        resp["provider"] = "mock"
        if not MOCK_SMS_MODE:
            resp["provider_error"] = provider_msg
    # Expose OTP in response ONLY when explicitly enabled (dev/CI), or as a
    # safety net when SMS could not be delivered so users aren't locked out.
    if TEST_RETURN_OTP or not sent:
        resp["mock_otp"] = otp_code
    return resp


@router.post("/profile/phone/verify-otp")
async def phone_verify_otp(body: PhoneOtpVerifyBody, u: dict = Depends(current_user)):
    # Iteration 60: `send-otp` stores the OTP row keyed on the E.164-normalised phone
    # (e.g. "+919525852855"). But some frontends may send the raw 10-digit form (e.g.
    # "9525852855") back to verify. Normalise here so both formats match the stored row.
    normalized, err = normalize_indian_mobile(body.phone or "")
    if err:
        raise HTTPException(status_code=400, detail=err)
    phone = normalized
    # Also match legacy rows that were saved with the raw input before this normalisation.
    raw_input = (body.phone or "").strip()
    otp_doc = await db.otps.find_one(
        {
            "user_id": u["id"],
            "phone": {"$in": [phone, raw_input]} if raw_input and raw_input != phone else phone,
            "purpose": "verify_phone",
            "consumed": False,
            "expires_at": {"$gt": now_ts()},
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not otp_doc:
        raise HTTPException(status_code=400, detail="OTP invalid or expired")
    if not verify_password(body.otp, otp_doc["otp_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect OTP")
    await db.otps.update_one({"id": otp_doc["id"]}, {"$set": {"consumed": True}})
    profile = dict(u.get("profile", {}) or {})
    profile["phone"] = phone
    profile["phone_verified"] = True
    profile["phone_verified_at"] = now_iso()
    update = {"profile": profile}
    if u["role"] == "student":
        update["profile_complete"] = is_student_complete(profile)
    await db.users.update_one({"id": u["id"]}, {"$set": update})
    u2 = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    return {"message": "Phone verified", "user": user_public(u2), "profile": u2.get("profile", {})}


# ------------------- Login / Forgot / Reset / Google / Me -------------------
@router.post("/auth/login")
async def login(body: LoginBody):
    u = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if u.get("account_status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended. Please contact support.")
    if not u.get("is_email_verified") and u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Email not verified")
    token = create_jwt(u["id"], u["role"])
    return {"token": token, "user": user_public(u)}


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotBody):
    u = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if u:
        otp_code = f"{secrets.randbelow(10**6):06d}"
        await db.otps.insert_one({
            "id": new_id(),
            "email": body.email.lower(),
            "otp_hash": hash_password(otp_code),
            "purpose": "reset_password",
            "expires_at": now_ts() + 600,
            "consumed": False,
            "created_at": now_iso(),
        })
        sent = await send_otp_email(body.email.lower(), otp_code, "reset_password")
        resp = {"message": "If account exists, OTP has been sent."}
        if MOCK_OTP_MODE or not sent or TEST_RETURN_OTP:
            resp["mock_otp"] = otp_code
        return resp
    return {"message": "If account exists, OTP has been sent."}


@router.post("/auth/reset-password")
async def reset_password(body: ResetBody):
    otp_doc = await db.otps.find_one(
        {
            "email": body.email.lower(),
            "purpose": "reset_password",
            "consumed": False,
            "expires_at": {"$gt": now_ts()},
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not otp_doc or not verify_password(body.otp, otp_doc["otp_hash"]):
        raise HTTPException(status_code=400, detail="OTP invalid or expired")
    await db.otps.update_one({"id": otp_doc["id"]}, {"$set": {"consumed": True}})
    await db.users.update_one(
        {"email": body.email.lower()},
        {"$set": {"password_hash": hash_password(body.new_password)}},
    )
    return {"message": "Password reset successful"}


@router.post("/auth/google")
async def google_login(body: GoogleSessionBody):
    """Exchange Emergent session_id for app JWT (Emergent-managed Google login)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.get(EMERGENT_AUTH_URL, headers={"X-Session-ID": body.session_id})
            if r.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid Google session")
            data = r.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Google session error: %s", e)
        raise HTTPException(status_code=502, detail="Auth provider unreachable")
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email missing from provider")
    u = await db.users.find_one({"email": email}, {"_id": 0})
    if not u:
        role = body.role or "student"
        u = {
            "id": new_id(),
            "email": email,
            "password_hash": hash_password(secrets.token_urlsafe(16)),
            "role": role,
            "name": data.get("name") or "",
            "is_email_verified": True,
            "credits": 100 if role == "student" else 0,
            "free_uses_left": 0 if role == "student" else (FREE_TIER_ACTIONS * 2),
            "total_deposits": 0,
            "profile_complete": False,
            "profile": {"picture": data.get("picture")},
            "google_id": data.get("id"),
            "created_at": now_iso(),
        }
        await db.users.insert_one(u)
        if role == "student":
            await db.transactions.insert_one({
                "id": new_id(),
                "user_id": u["id"],
                "delta": 100,
                "reason": "signup_bonus",
                "meta": {"label": "Signup Bonus - 100 Credits"},
                "created_at": now_iso(),
            })
        u.pop("_id", None)
    token = create_jwt(u["id"], u["role"])
    return {"token": token, "user": user_public(u)}


@router.get("/auth/me")
async def get_me(u: dict = Depends(current_user)):
    out = {"user": user_public(u), "profile": u.get("profile", {})}
    if u["role"] == "professional":
        out["profile_completion"] = compute_pro_profile_completion(u)
        out["missing_fields"] = pro_missing_fields(u)
        out["user"]["gmail_verified"] = bool(u.get("gmail_verified"))
        out["user"]["alternate_gmail"] = u.get("alternate_gmail") or (u.get("profile", {}) or {}).get("alternate_gmail")
        out["user"]["email_verified"] = True  # company email verified at signup
    elif u["role"] == "student":
        # Iteration 58 — profile completion gate for Job Application flow.
        out["profile_completion"] = student_profile_completion(u)
        out["missing_fields"] = student_missing_fields(u)
    return out


# ------------------- Pro alternate-Gmail OTP -------------------
@router.post("/pro/gmail/send-otp")
async def pro_gmail_send_otp(body: GmailVerifyBody, u: dict = Depends(require_role(["professional"]))):
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    personal_domains = {"gmail.com", "googlemail.com"}
    domain = email.split("@", 1)[1]
    if domain not in personal_domains:
        raise HTTPException(status_code=400, detail="Please provide a personal Gmail address (gmail.com).")
    if email == (u.get("email") or "").lower():
        raise HTTPException(status_code=400, detail="Use a DIFFERENT email from your company login email.")
    otp_code = f"{secrets.randbelow(10**6):06d}"
    await db.otps.insert_one({
        "id": new_id(),
        "user_id": u["id"],
        "email": email,
        "purpose": "verify_alternate_gmail",
        "code_hash": hash_password(otp_code),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "consumed": False,
        "created_at": now_iso(),
    })
    sent = await send_otp_email(email, otp_code, "verify_alternate_gmail")
    resp = {"message": "OTP sent to your Gmail", "email_sent": bool(sent)}
    if MOCK_OTP_MODE or not sent or TEST_RETURN_OTP:
        resp["mock_otp"] = otp_code
    return resp


@router.post("/pro/gmail/verify-otp")
async def pro_gmail_verify_otp(body: GmailVerifyBody, u: dict = Depends(require_role(["professional"]))):
    email = (body.email or "").strip().lower()
    code = (body.otp or "").strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="email + otp required")
    otp = await db.otps.find_one(
        {"user_id": u["id"], "email": email, "purpose": "verify_alternate_gmail", "consumed": False},
        sort=[("created_at", -1)],
    )
    if not otp:
        raise HTTPException(status_code=400, detail="No OTP pending. Please request a fresh one.")
    if datetime.fromisoformat(otp["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
    if not verify_password(code, otp["code_hash"]):
        raise HTTPException(status_code=400, detail="Invalid OTP")
    await db.otps.update_one({"id": otp["id"]}, {"$set": {"consumed": True}})
    new_profile = {**(u.get("profile", {}) or {}), "alternate_gmail": email}
    await db.users.update_one(
        {"id": u["id"]},
        {"$set": {
            "alternate_gmail": email,
            "gmail_verified": True,
            "gmail_verified_at": now_iso(),
            "profile": new_profile,
        }},
    )
    await push_notification(u["id"], "Gmail verified ✅", f"{email} is now linked for interview invites.", "success")
    return {"message": "Gmail verified", "alternate_gmail": email}
