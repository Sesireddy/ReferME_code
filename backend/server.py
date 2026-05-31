"""ReferME backend: Auth (JWT+OTP, Emergent Google), profiles, wallet, mock
interviews, referrals, jobs, leaderboards, payouts, admin, notifications."""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import bcrypt
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MIN = int(os.environ.get("JWT_ACCESS_EXPIRES_MIN", "10080"))
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "no-reply@referme.app")
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@referme.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
EMERGENT_AUTH_URL = os.environ.get(
    "EMERGENT_AUTH_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)

MOCK_OTP_MODE = not bool(SENDGRID_API_KEY)
MOCK_PAYMENTS_MODE = not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)

# Business rules
ACTION_COST = 49  # credits per action (apply / book)
INTERVIEW_PRO_REWARD = 25
REFERRAL_HIRED_REWARD = 500
PAYOUT_MIN = 500
FIRST_DEPOSIT_MIN_INR = 199
FIRST_DEPOSIT_BONUS_CREDITS = 398  # ₹199 → 398 credits
FREE_TIER_ACTIONS = 1  # 1 referral + 1 mock interview free

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("referme")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="ReferME API")
api = APIRouter(prefix="/api")


# ------------------- Utility helpers -------------------
def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_jwt(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MIN),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def new_id() -> str:
    return str(uuid.uuid4())


def user_public(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "role": u["role"],
        "name": u.get("name", ""),
        "is_email_verified": u.get("is_email_verified", False),
        "credits": u.get("credits", 0),
        "profile_complete": u.get("profile_complete", False),
        "free_uses_left": u.get("free_uses_left", FREE_TIER_ACTIONS * 2),
        "total_deposits": u.get("total_deposits", 0),
        "created_at": u.get("created_at", now_iso()),
    }


async def send_otp_email(email: str, otp: str, purpose: str) -> None:
    """Send OTP email via SendGrid, fall back to logging in mock mode."""
    subject = "ReferME Verification Code" if purpose == "verify_email" else "ReferME Password Reset Code"
    if MOCK_OTP_MODE:
        logger.info("[MOCK-EMAIL] to=%s purpose=%s otp=%s", email, purpose, otp)
        return
    try:
        from sendgrid import SendGridAPIClient  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        msg = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=email,
            subject=subject,
            html_content=f"<p>Your ReferME code is <b>{otp}</b>. It expires in 10 minutes.</p>",
        )
        SendGridAPIClient(SENDGRID_API_KEY).send(msg)
    except Exception as e:
        logger.warning("SendGrid send failed: %s", e)


async def push_notification(user_id: str, title: str, body: str, kind: str = "info") -> None:
    await db.notifications.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "title": title,
        "body": body,
        "kind": kind,
        "read": False,
        "created_at": now_iso(),
    })


# ------------------- Models -------------------
Role = Literal["student", "professional", "employer", "admin"]


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: Role
    name: Optional[str] = ""


class VerifyOtpBody(BaseModel):
    email: EmailStr
    otp: str
    purpose: Literal["verify_email", "reset_password"] = "verify_email"


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ForgotBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=6)


class GoogleSessionBody(BaseModel):
    session_id: str
    role: Optional[Role] = "student"


class ProfileBody(BaseModel):
    name: Optional[str] = None
    # student / job-seeker
    education: Optional[str] = None  # e.g. "B.Tech" | "Degree" | "M.Tech" | "MBA" | "Others"
    education_details: Optional[str] = None  # when education == "Others" or extra detail
    passed_out_year: Optional[int] = None
    current_location: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
    preferred_role: Optional[Literal["fresher", "experienced"]] = None
    years_of_experience: Optional[int] = None  # for experienced
    skills: Optional[list[str]] = None
    resume_base64: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_size: Optional[int] = None
    resume_mime_type: Optional[str] = None  # "application/pdf" | "application/msword" | "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    resume_link: Optional[str] = None  # external URL alternative
    # professional
    company: Optional[str] = None
    designation: Optional[str] = None
    experience_years: Optional[int] = None
    expertise: Optional[list[str]] = None
    # employer
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_size: Optional[str] = None
    company_logo_base64: Optional[str] = None
    bio: Optional[str] = None


class InterviewSlotBody(BaseModel):
    start_at: str  # ISO
    end_at: str    # ISO
    topic: Optional[str] = ""


class DepositBody(BaseModel):
    amount_inr: int = Field(ge=1)


class VerifyPaymentBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class BookInterviewBody(BaseModel):
    slot_id: str


class JobPostBody(BaseModel):
    title: str
    description: str
    location: Optional[str] = ""
    salary_range: Optional[str] = ""
    skills_required: Optional[list[str]] = []
    bulk_openings: int = 1


class ApplyJobBody(BaseModel):
    job_id: str


class ReferBody(BaseModel):
    student_id: str
    job_id: str
    note: Optional[str] = ""


class HireBody(BaseModel):
    application_id: str


class PayoutBody(BaseModel):
    amount_inr: int = Field(ge=PAYOUT_MIN)
    upi_or_account: str


class AdminActionBody(BaseModel):
    payout_id: str
    action: Literal["approve", "reject"]
    note: Optional[str] = ""


class DisputeBody(BaseModel):
    subject: str
    description: str


# ------------------- Auth dependency -------------------
async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    u = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return u


def require_role(roles: list[Role]):
    async def _dep(u: dict = Depends(current_user)):
        if u["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return u
    return _dep


def admin_only(u: dict = Depends(current_user)) -> dict:
    if u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return u


# ------------------- Routes: Health & Auth -------------------
@api.get("/")
async def root():
    return {"app": "ReferME", "mock_otp": MOCK_OTP_MODE, "mock_payments": MOCK_PAYMENTS_MODE}


@api.post("/auth/signup")
async def signup(body: SignupBody):
    if body.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot self-register as admin")
    existing = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "id": new_id(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "role": body.role,
        "name": body.name or "",
        "is_email_verified": False,
        "credits": 0,
        "free_uses_left": FREE_TIER_ACTIONS * 2,
        "total_deposits": 0,
        "profile_complete": False,
        "profile": {},
        "created_at": now_iso(),
    }
    await db.users.insert_one(user_doc)
    otp_code = f"{secrets.randbelow(10**6):06d}"
    await db.otps.insert_one({
        "id": new_id(),
        "email": body.email.lower(),
        "otp_hash": hash_password(otp_code),
        "purpose": "verify_email",
        "expires_at": now_ts() + 600,
        "consumed": False,
        "created_at": now_iso(),
    })
    await send_otp_email(body.email.lower(), otp_code, "verify_email")
    resp = {"message": "Signup successful. OTP sent.", "email": body.email.lower()}
    if MOCK_OTP_MODE:
        resp["mock_otp"] = otp_code  # only in mock mode for testing
    return resp


@api.post("/auth/verify-otp")
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
        return {"token": token, "user": user_public(u)}
    return {"message": "OTP verified", "reset_token": body.otp}


@api.post("/auth/login")
async def login(body: LoginBody):
    u = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not u.get("is_email_verified") and u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Email not verified")
    token = create_jwt(u["id"], u["role"])
    return {"token": token, "user": user_public(u)}


@api.post("/auth/forgot-password")
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
        await send_otp_email(body.email.lower(), otp_code, "reset_password")
        resp = {"message": "If account exists, OTP has been sent."}
        if MOCK_OTP_MODE:
            resp["mock_otp"] = otp_code
        return resp
    return {"message": "If account exists, OTP has been sent."}


@api.post("/auth/reset-password")
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


@api.post("/auth/google")
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
        u = {
            "id": new_id(),
            "email": email,
            "password_hash": hash_password(secrets.token_urlsafe(16)),
            "role": body.role or "student",
            "name": data.get("name") or "",
            "is_email_verified": True,
            "credits": 0,
            "free_uses_left": FREE_TIER_ACTIONS * 2,
            "total_deposits": 0,
            "profile_complete": False,
            "profile": {"picture": data.get("picture")},
            "google_id": data.get("id"),
            "created_at": now_iso(),
        }
        await db.users.insert_one(u)
        u.pop("_id", None)
    token = create_jwt(u["id"], u["role"])
    return {"token": token, "user": user_public(u)}


@api.get("/auth/me")
async def get_me(u: dict = Depends(current_user)):
    return {"user": user_public(u), "profile": u.get("profile", {})}


STUDENT_PROFILE_FIELDS = [
    "education", "education_details", "passed_out_year", "current_location",
    "dob", "preferred_role", "years_of_experience", "skills",
    "resume_base64", "resume_filename", "resume_size", "resume_mime_type", "resume_link",
]
PRO_PROFILE_FIELDS = ["company", "designation", "experience_years", "expertise"]
EMPLOYER_PROFILE_FIELDS = ["company_name", "company_website", "company_size", "company_logo_base64", "bio"]


def compute_resume_score(user: dict) -> int:
    """Resume score 0-100 driven by mock interviews attended + profile completeness."""
    profile = user.get("profile", {}) or {}
    attended = int(user.get("interviews_attended", 0) or 0)
    fields = ["education", "passed_out_year", "current_location", "dob", "preferred_role", "skills"]
    has_resume = bool(profile.get("resume_base64") or profile.get("resume_link"))
    completeness = sum(1 for f in fields if profile.get(f))
    score = (15 if has_resume else 0) + completeness * 3 + attended * 12
    return max(0, min(100, int(score)))


def is_student_complete(profile: dict) -> bool:
    required = ["education", "passed_out_year", "current_location", "preferred_role", "skills"]
    has_resume = bool(profile.get("resume_base64") or profile.get("resume_link"))
    if not has_resume:
        return False
    for r in required:
        if not profile.get(r):
            return False
    if profile.get("preferred_role") == "experienced" and not profile.get("years_of_experience"):
        return False
    if profile.get("education") == "Others" and not profile.get("education_details"):
        return False
    return True


# ------------------- Profile -------------------
@api.put("/profile")
async def update_profile(body: ProfileBody, u: dict = Depends(current_user)):
    profile = dict(u.get("profile", {}) or {})
    update_fields: dict[str, Any] = {}
    role = u["role"]
    payload = body.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        update_fields["name"] = payload["name"]
    role_fields = {
        "student": STUDENT_PROFILE_FIELDS,
        "professional": PRO_PROFILE_FIELDS,
        "employer": EMPLOYER_PROFILE_FIELDS,
    }.get(role, [])
    for k in role_fields:
        if k in payload:
            profile[k] = payload[k]  # allow None to clear

    # Auto compute completion
    if role == "student":
        complete = is_student_complete(profile)
        # auto-update resume_score from interviews attended
        merged_user = {**u, "profile": profile}
        profile["resume_score"] = compute_resume_score(merged_user)
    elif role == "professional":
        complete = bool(profile.get("company") and profile.get("designation") and profile.get("expertise"))
    elif role == "employer":
        complete = bool(profile.get("company_name") and profile.get("company_size"))
    else:
        complete = True

    update_fields["profile"] = profile
    update_fields["profile_complete"] = complete
    await db.users.update_one({"id": u["id"]}, {"$set": update_fields})
    u2 = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    return {"user": user_public(u2), "profile": u2.get("profile", {})}


# ------------------- Wallet & Subscription -------------------
@api.get("/wallet")
async def get_wallet(u: dict = Depends(current_user)):
    txs = await db.transactions.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "credits": u.get("credits", 0),
        "free_uses_left": u.get("free_uses_left", 0),
        "total_deposits": u.get("total_deposits", 0),
        "transactions": txs,
    }


@api.get("/subscription/plans")
async def subscription_plans(u: dict = Depends(current_user)):
    is_first = (u.get("total_deposits", 0) == 0)
    return {
        "free_tier": {
            "title": "Free Tier",
            "description": "1 referral application + 1 mock interview",
            "free_uses_left": u.get("free_uses_left", 0),
        },
        "paid_tier": {
            "title": "Paid Credits",
            "is_first_deposit": is_first,
            "first_deposit_inr": FIRST_DEPOSIT_MIN_INR,
            "first_deposit_credits": FIRST_DEPOSIT_BONUS_CREDITS,
            "subsequent_rate": "1 INR = 1 credit",
            "action_cost": ACTION_COST,
        },
    }


async def _credit_user(user_id: str, delta: int, reason: str, meta: Optional[dict] = None) -> int:
    res = await db.users.find_one_and_update(
        {"id": user_id},
        {"$inc": {"credits": delta}},
        return_document=True,
        projection={"_id": 0, "credits": 1},
    )
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "delta": delta,
        "reason": reason,
        "meta": meta or {},
        "created_at": now_iso(),
    })
    return res["credits"] if res else 0


@api.post("/wallet/deposit/create-order")
async def create_deposit_order(body: DepositBody, u: dict = Depends(require_role(["student", "professional", "employer"]))):
    if body.amount_inr < 1:
        raise HTTPException(status_code=400, detail="Amount must be ≥ ₹1")
    is_first = (u.get("total_deposits", 0) == 0)
    if is_first and body.amount_inr < FIRST_DEPOSIT_MIN_INR:
        raise HTTPException(status_code=400, detail=f"First deposit must be ≥ ₹{FIRST_DEPOSIT_MIN_INR}")
    order_id = f"order_{new_id()[:18]}"
    credits = FIRST_DEPOSIT_BONUS_CREDITS if (is_first and body.amount_inr == FIRST_DEPOSIT_MIN_INR) else body.amount_inr
    if is_first and body.amount_inr > FIRST_DEPOSIT_MIN_INR:
        # First-time bonus only on exact ₹199, otherwise 1:1
        credits = body.amount_inr * 2 if body.amount_inr == FIRST_DEPOSIT_MIN_INR else body.amount_inr
    doc = {
        "id": new_id(),
        "razorpay_order_id": order_id,
        "user_id": u["id"],
        "amount_inr": body.amount_inr,
        "credits_to_grant": credits,
        "status": "created",
        "is_first_deposit": is_first,
        "mock": MOCK_PAYMENTS_MODE,
        "created_at": now_iso(),
    }
    await db.deposit_orders.insert_one(doc)
    return {
        "order_id": doc["id"],
        "razorpay_order_id": order_id,
        "amount_inr": body.amount_inr,
        "credits_to_grant": credits,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "mock": MOCK_PAYMENTS_MODE,
    }


@api.post("/wallet/deposit/confirm")
async def confirm_deposit(body: VerifyPaymentBody, u: dict = Depends(current_user)):
    """In mock mode, accept any signature. In real mode, verify HMAC."""
    order = await db.deposit_orders.find_one({"razorpay_order_id": body.razorpay_order_id}, {"_id": 0})
    if not order or order["user_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "paid":
        return {"message": "Already credited", "credits": u["credits"]}
    if not MOCK_PAYMENTS_MODE:
        import hashlib, hmac
        msg = f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode()
        expected = hmac.new(RAZORPAY_KEY_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        if expected != body.razorpay_signature:
            raise HTTPException(status_code=400, detail="Invalid signature")
    await db.deposit_orders.update_one(
        {"id": order["id"]},
        {"$set": {"status": "paid", "razorpay_payment_id": body.razorpay_payment_id, "updated_at": now_iso()}},
    )
    credits = order["credits_to_grant"]
    new_balance = await _credit_user(u["id"], credits, "deposit", {"order_id": order["id"], "amount_inr": order["amount_inr"]})
    await db.users.update_one({"id": u["id"]}, {"$inc": {"total_deposits": 1}})
    await push_notification(u["id"], "Credits added 💰", f"+{credits} credits added to your wallet.", "success")
    return {"message": "Payment confirmed", "credits": new_balance, "added": credits}


# ------------------- Mock Interviews -------------------
@api.get("/professionals")
async def list_professionals(u: dict = Depends(current_user)):
    pros = await db.users.find({"role": "professional", "profile_complete": True}, {"_id": 0, "password_hash": 0}).to_list(100)
    return [
        {
            "id": p["id"],
            "name": p.get("name") or p["email"].split("@")[0],
            "company": p.get("profile", {}).get("company"),
            "designation": p.get("profile", {}).get("designation"),
            "experience_years": p.get("profile", {}).get("experience_years"),
            "expertise": p.get("profile", {}).get("expertise", []),
        }
        for p in pros
    ]


@api.post("/interviews/slots")
async def create_slot(body: InterviewSlotBody, u: dict = Depends(require_role(["professional"]))):
    try:
        start = datetime.fromisoformat(body.start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(body.end_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    if end <= start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    if (end - start).total_seconds() < 15 * 60:
        raise HTTPException(status_code=400, detail="Slot must be at least 15 minutes")
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Slot must be in the future")

    # Conflict check: any existing non-cancelled slot for this pro overlapping?
    existing = await db.interview_slots.find(
        {"pro_id": u["id"], "status": {"$in": ["available", "booked"]}},
        {"_id": 0},
    ).to_list(500)
    for s in existing:
        try:
            es = datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
            ee = datetime.fromisoformat(s["end_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if start < ee and end > es:
            raise HTTPException(
                status_code=400,
                detail=f"Conflicts with existing slot {es.strftime('%d %b %H:%M')} – {ee.strftime('%H:%M')}",
            )

    slot = {
        "id": new_id(),
        "pro_id": u["id"],
        "pro_name": u.get("name") or u["email"].split("@")[0],
        "start_at": body.start_at,
        "end_at": body.end_at,
        # Keep legacy alias for any clients still reading scheduled_at
        "scheduled_at": body.start_at,
        "topic": body.topic or "",
        "status": "available",
        "student_id": None,
        "student_name": None,
        "created_at": now_iso(),
    }
    await db.interview_slots.insert_one(slot)
    return {k: v for k, v in slot.items() if k != "_id"}


@api.get("/interviews/slots")
async def list_slots(pro_id: Optional[str] = Query(None), u: dict = Depends(current_user)):
    q: dict = {}
    if pro_id:
        q["pro_id"] = pro_id
    if u["role"] == "professional":
        q["pro_id"] = u["id"]
    elif u["role"] == "student" and not pro_id:
        q["status"] = "available"
    slots = await db.interview_slots.find(q, {"_id": 0}).sort("start_at", 1).to_list(200)
    return slots


def _can_use_free(u: dict, kind: str) -> bool:
    return u.get("free_uses_left", 0) > 0


@api.post("/interviews/book")
async def book_interview(body: BookInterviewBody, u: dict = Depends(require_role(["student"]))):
    slot = await db.interview_slots.find_one({"id": body.slot_id}, {"_id": 0})
    if not slot or slot["status"] != "available":
        raise HTTPException(status_code=400, detail="Slot not available")
    use_free = _can_use_free(u, "interview")
    if not use_free and u.get("credits", 0) < ACTION_COST:
        raise HTTPException(status_code=400, detail="Insufficient credits")
    if use_free:
        await db.users.update_one({"id": u["id"]}, {"$inc": {"free_uses_left": -1}})
    else:
        await _credit_user(u["id"], -ACTION_COST, "interview_booking", {"slot_id": slot["id"]})
    await db.interview_slots.update_one(
        {"id": slot["id"]},
        {"$set": {"status": "booked", "student_id": u["id"], "student_name": u.get("name") or u["email"].split("@")[0]}},
    )
    await push_notification(u["id"], "Interview booked ✅", f"With {slot['pro_name']} at {slot['scheduled_at']}", "success")
    await push_notification(slot["pro_id"], "New interview booked", f"Student booked your slot at {slot['scheduled_at']}", "info")
    return {"message": "Booked", "used_free": use_free}


@api.post("/interviews/{slot_id}/complete")
async def complete_interview(slot_id: str, u: dict = Depends(require_role(["professional"]))):
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot or slot["pro_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["status"] != "booked":
        raise HTTPException(status_code=400, detail="Slot not booked")
    await db.interview_slots.update_one({"id": slot_id}, {"$set": {"status": "completed", "completed_at": now_iso()}})
    await _credit_user(u["id"], INTERVIEW_PRO_REWARD, "interview_conducted", {"slot_id": slot_id})
    # Increment student interviews_attended and refresh resume score
    student = await db.users.find_one_and_update(
        {"id": slot["student_id"]},
        {"$inc": {"interviews_attended": 1}},
        return_document=True,
        projection={"_id": 0},
    )
    if student:
        new_score = compute_resume_score(student)
        new_profile = {**(student.get("profile", {}) or {}), "resume_score": new_score}
        await db.users.update_one({"id": student["id"]}, {"$set": {"profile": new_profile}})
        await push_notification(
            student["id"],
            "Interview completed 🎓",
            f"Your resume score is now {new_score}/100. Keep going!",
            "success",
        )
    await db.users.update_one({"id": u["id"]}, {"$inc": {"interviews_conducted": 1}})
    await push_notification(u["id"], "Earned +25 credits 🎯", "Interview marked completed.", "success")
    return {"message": "Completed", "earned": INTERVIEW_PRO_REWARD}


# ------------------- Jobs & Applications & Referrals -------------------
@api.post("/jobs")
async def post_job(body: JobPostBody, u: dict = Depends(require_role(["employer"]))):
    job = {
        "id": new_id(),
        "employer_id": u["id"],
        "employer_name": u.get("profile", {}).get("company_name") or u.get("name") or "Employer",
        "title": body.title,
        "description": body.description,
        "location": body.location,
        "salary_range": body.salary_range,
        "skills_required": body.skills_required or [],
        "bulk_openings": body.bulk_openings,
        "status": "open",
        "created_at": now_iso(),
    }
    await db.jobs.insert_one(job)
    return {k: v for k, v in job.items() if k != "_id"}


@api.get("/jobs")
async def list_jobs(u: dict = Depends(current_user)):
    q: dict = {}
    if u["role"] == "employer":
        q["employer_id"] = u["id"]
    else:
        q["status"] = "open"
    jobs = await db.jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    # Annotate `applied` flag for students
    if u["role"] == "student" and jobs:
        my_apps = await db.applications.find({"student_id": u["id"]}, {"_id": 0, "job_id": 1, "status": 1}).to_list(1000)
        by_job = {a["job_id"]: a["status"] for a in my_apps}
        for j in jobs:
            j["applied"] = j["id"] in by_job
            j["application_status"] = by_job.get(j["id"])
    return jobs


@api.post("/jobs/apply")
async def apply_job(body: ApplyJobBody, u: dict = Depends(require_role(["student"]))):
    job = await db.jobs.find_one({"id": body.job_id}, {"_id": 0})
    if not job or job["status"] != "open":
        raise HTTPException(status_code=400, detail="Job not available")
    existing = await db.applications.find_one({"job_id": job["id"], "student_id": u["id"]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Already applied")
    use_free = _can_use_free(u, "referral")
    if not use_free and u.get("credits", 0) < ACTION_COST:
        raise HTTPException(status_code=400, detail="Insufficient credits")
    if use_free:
        await db.users.update_one({"id": u["id"]}, {"$inc": {"free_uses_left": -1}})
    else:
        await _credit_user(u["id"], -ACTION_COST, "job_application", {"job_id": job["id"]})
    app_doc = {
        "id": new_id(),
        "job_id": job["id"],
        "job_title": job["title"],
        "employer_id": job["employer_id"],
        "student_id": u["id"],
        "student_name": u.get("name") or u["email"].split("@")[0],
        "referrer_pro_id": None,
        "status": "applied",  # applied -> shortlisted -> hired / rejected
        "created_at": now_iso(),
    }
    await db.applications.insert_one(app_doc)
    await push_notification(u["id"], "Application sent ✉️", f"Applied to {job['title']}", "success")
    await push_notification(job["employer_id"], "New applicant", f"For {job['title']}", "info")
    return {"message": "Applied", "used_free": use_free}


@api.post("/referrals")
async def refer_student(body: ReferBody, u: dict = Depends(require_role(["professional"]))):
    student = await db.users.find_one({"id": body.student_id, "role": "student"}, {"_id": 0})
    job = await db.jobs.find_one({"id": body.job_id, "status": "open"}, {"_id": 0})
    if not student or not job:
        raise HTTPException(status_code=400, detail="Student or job not found")
    existing = await db.applications.find_one({"job_id": job["id"], "student_id": student["id"]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Application already exists")
    app_doc = {
        "id": new_id(),
        "job_id": job["id"],
        "job_title": job["title"],
        "employer_id": job["employer_id"],
        "student_id": student["id"],
        "student_name": student.get("name") or student["email"].split("@")[0],
        "referrer_pro_id": u["id"],
        "referrer_pro_name": u.get("name") or u["email"].split("@")[0],
        "note": body.note,
        "status": "referred",
        "created_at": now_iso(),
    }
    await db.applications.insert_one(app_doc)
    await db.users.update_one({"id": u["id"]}, {"$inc": {"referrals_made": 1}})
    await push_notification(student["id"], "You've been referred 🌟", f"{u.get('name') or 'A professional'} referred you for {job['title']}", "success")
    await push_notification(job["employer_id"], "New referral", f"For {job['title']}", "info")
    return {"message": "Referral created", "application_id": app_doc["id"]}


@api.get("/applications")
async def list_applications(u: dict = Depends(current_user)):
    if u["role"] == "student":
        q = {"student_id": u["id"]}
    elif u["role"] == "employer":
        q = {"employer_id": u["id"]}
    elif u["role"] == "professional":
        q = {"referrer_pro_id": u["id"]}
    else:
        q = {}
    apps = await db.applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return apps


@api.get("/applications/pool")
async def applications_pool(_: dict = Depends(require_role(["professional"]))):
    """All applicants across the platform — pros browse to refer candidates."""
    apps = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Hydrate with student profile snippet
    student_ids = list({a["student_id"] for a in apps})
    students = await db.users.find(
        {"id": {"$in": student_ids}},
        {"_id": 0, "password_hash": 0},
    ).to_list(1000)
    sm = {s["id"]: s for s in students}
    out = []
    for a in apps:
        s = sm.get(a["student_id"], {})
        profile = s.get("profile", {}) or {}
        out.append({
            **a,
            "student_profile": {
                "education": profile.get("education"),
                "education_details": profile.get("education_details"),
                "passed_out_year": profile.get("passed_out_year"),
                "current_location": profile.get("current_location"),
                "preferred_role": profile.get("preferred_role"),
                "years_of_experience": profile.get("years_of_experience"),
                "skills": profile.get("skills", []),
                "resume_score": profile.get("resume_score", 0),
                "resume_filename": profile.get("resume_filename"),
                "resume_link": profile.get("resume_link"),
            },
            "interviews_attended": s.get("interviews_attended", 0),
        })
    return out


@api.post("/applications/hire")
async def hire_candidate(body: HireBody, u: dict = Depends(require_role(["employer"]))):
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc or appdoc["employer_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    if appdoc["status"] == "hired":
        raise HTTPException(status_code=400, detail="Already hired")
    await db.applications.update_one({"id": appdoc["id"]}, {"$set": {"status": "hired", "hired_at": now_iso()}})
    await push_notification(appdoc["student_id"], "You're hired! 🎉", f"For {appdoc['job_title']}", "success")
    if appdoc.get("referrer_pro_id"):
        await _credit_user(appdoc["referrer_pro_id"], REFERRAL_HIRED_REWARD, "referral_hired", {"application_id": appdoc["id"]})
        await db.users.update_one({"id": appdoc["referrer_pro_id"]}, {"$inc": {"successful_referrals": 1}})
        await push_notification(appdoc["referrer_pro_id"], "Referral bonus 💸", f"+{REFERRAL_HIRED_REWARD} credits — your candidate was hired!", "success")
    return {"message": "Candidate hired"}


# ------------------- Leaderboards -------------------
@api.get("/leaderboard/students")
async def leaderboard_students(u: dict = Depends(current_user)):
    students = await db.users.find({"role": "student"}, {"_id": 0, "password_hash": 0}).to_list(1000)
    def score(s: dict) -> int:
        return (s.get("interviews_attended", 0) * 10) + int((s.get("profile", {}).get("resume_score") or 0))
    students.sort(key=score, reverse=True)
    return [
        {
            "rank": i + 1,
            "id": s["id"],
            "name": s.get("name") or s["email"].split("@")[0],
            "score": score(s),
            "interviews_attended": s.get("interviews_attended", 0),
            "resume_score": s.get("profile", {}).get("resume_score") or 0,
            "is_me": s["id"] == u["id"],
        }
        for i, s in enumerate(students[:50])
    ]


@api.get("/leaderboard/professionals")
async def leaderboard_pros(u: dict = Depends(current_user)):
    pros = await db.users.find({"role": "professional"}, {"_id": 0, "password_hash": 0}).to_list(1000)
    def score(p: dict) -> int:
        return p.get("interviews_conducted", 0) * 5 + p.get("referrals_made", 0) * 3 + p.get("successful_referrals", 0) * 20
    pros.sort(key=score, reverse=True)
    return [
        {
            "rank": i + 1,
            "id": p["id"],
            "name": p.get("name") or p["email"].split("@")[0],
            "score": score(p),
            "interviews_conducted": p.get("interviews_conducted", 0),
            "referrals_made": p.get("referrals_made", 0),
            "successful_referrals": p.get("successful_referrals", 0),
            "is_me": p["id"] == u["id"],
        }
        for i, p in enumerate(pros[:50])
    ]


# ------------------- Payouts -------------------
@api.post("/payouts/request")
async def request_payout(body: PayoutBody, u: dict = Depends(require_role(["professional"]))):
    if u.get("credits", 0) < body.amount_inr:
        raise HTTPException(status_code=400, detail="Insufficient credits")
    if u.get("credits", 0) < PAYOUT_MIN:
        raise HTTPException(status_code=400, detail=f"Minimum {PAYOUT_MIN} credits required")
    doc = {
        "id": new_id(),
        "professional_id": u["id"],
        "professional_name": u.get("name") or u["email"].split("@")[0],
        "amount_inr": body.amount_inr,
        "upi_or_account": body.upi_or_account,
        "status": "requested",
        "admin_note": "",
        "created_at": now_iso(),
    }
    # Hold credits immediately
    await _credit_user(u["id"], -body.amount_inr, "payout_hold", {"payout_id": doc["id"]})
    await db.payouts.insert_one(doc)
    await push_notification(u["id"], "Payout requested 💰", f"₹{body.amount_inr} pending admin approval.", "info")
    return {"message": "Payout requested", "payout_id": doc["id"]}


@api.get("/payouts")
async def list_payouts(u: dict = Depends(current_user)):
    q = {}
    if u["role"] == "professional":
        q["professional_id"] = u["id"]
    elif u["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    payouts = await db.payouts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return payouts


@api.post("/admin/payouts/action")
async def admin_payout_action(body: AdminActionBody, _: dict = Depends(admin_only)):
    p = await db.payouts.find_one({"id": body.payout_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payout not found")
    if p["status"] != "requested":
        raise HTTPException(status_code=400, detail="Already processed")
    if body.action == "approve":
        await db.payouts.update_one(
            {"id": body.payout_id},
            {"$set": {"status": "approved", "admin_note": body.note, "updated_at": now_iso()}},
        )
        await push_notification(p["professional_id"], "Payout approved ✅", f"₹{p['amount_inr']} on the way.", "success")
    else:
        # refund credits
        await _credit_user(p["professional_id"], p["amount_inr"], "payout_refund", {"payout_id": p["id"]})
        await db.payouts.update_one(
            {"id": body.payout_id},
            {"$set": {"status": "rejected", "admin_note": body.note, "updated_at": now_iso()}},
        )
        await push_notification(p["professional_id"], "Payout rejected ❌", body.note or "Please contact support.", "error")
    return {"message": f"Payout {body.action}d"}


# ------------------- Admin -------------------
@api.get("/admin/users")
async def admin_users(_: dict = Depends(admin_only)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return [user_public(u) for u in users]


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(admin_only)):
    return {
        "students": await db.users.count_documents({"role": "student"}),
        "professionals": await db.users.count_documents({"role": "professional"}),
        "employers": await db.users.count_documents({"role": "employer"}),
        "jobs": await db.jobs.count_documents({}),
        "applications": await db.applications.count_documents({}),
        "interviews": await db.interview_slots.count_documents({"status": "completed"}),
        "payouts_pending": await db.payouts.count_documents({"status": "requested"}),
        "disputes_open": await db.disputes.count_documents({"status": "open"}),
    }


@api.post("/disputes")
async def create_dispute(body: DisputeBody, u: dict = Depends(current_user)):
    doc = {
        "id": new_id(),
        "user_id": u["id"],
        "user_email": u["email"],
        "subject": body.subject,
        "description": body.description,
        "status": "open",
        "created_at": now_iso(),
    }
    await db.disputes.insert_one(doc)
    return {"message": "Dispute submitted", "id": doc["id"]}


@api.get("/disputes")
async def list_disputes(u: dict = Depends(current_user)):
    q = {} if u["role"] == "admin" else {"user_id": u["id"]}
    disputes = await db.disputes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return disputes


@api.post("/admin/disputes/{dispute_id}/resolve")
async def resolve_dispute(dispute_id: str, _: dict = Depends(admin_only)):
    res = await db.disputes.update_one({"id": dispute_id}, {"$set": {"status": "resolved", "updated_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return {"message": "Resolved"}


# ------------------- Notifications -------------------
@api.get("/notifications")
async def get_notifications(u: dict = Depends(current_user)):
    notes = await db.notifications.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return notes


@api.post("/notifications/read-all")
async def read_all(u: dict = Depends(current_user)):
    await db.notifications.update_many({"user_id": u["id"], "read": False}, {"$set": {"read": True}})
    return {"message": "All read"}


# ------------------- Startup -------------------
@app.on_event("startup")
async def on_startup() -> None:
    # Seed admin
    existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0})
    if not existing:
        await db.users.insert_one({
            "id": new_id(),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "role": "admin",
            "name": "ReferME Admin",
            "is_email_verified": True,
            "credits": 0,
            "free_uses_left": 0,
            "profile_complete": True,
            "profile": {},
            "total_deposits": 0,
            "created_at": now_iso(),
        })
        logger.info("Seeded admin user: %s", ADMIN_EMAIL)

    # Seed sample jobs / employer if empty for demo
    if await db.jobs.count_documents({}) == 0:
        # create demo employer if none
        emp = await db.users.find_one({"role": "employer"}, {"_id": 0})
        if not emp:
            emp = {
                "id": new_id(),
                "email": "demo-employer@referme.app",
                "password_hash": hash_password("Demo@12345"),
                "role": "employer",
                "name": "Acme Tech",
                "is_email_verified": True,
                "credits": 0,
                "free_uses_left": 0,
                "total_deposits": 0,
                "profile_complete": True,
                "profile": {"company_name": "Acme Tech", "company_size": "200-500", "company_website": "acme.tech"},
                "created_at": now_iso(),
            }
            await db.users.insert_one(emp)
        sample_jobs = [
            {"title": "Frontend Engineer", "description": "Build delightful React Native experiences.", "location": "Bengaluru", "salary_range": "₹15-25 LPA", "skills_required": ["React Native", "TypeScript"], "bulk_openings": 3},
            {"title": "Backend Engineer (Python)", "description": "Design scalable APIs.", "location": "Remote", "salary_range": "₹18-30 LPA", "skills_required": ["FastAPI", "MongoDB"], "bulk_openings": 2},
            {"title": "Product Designer", "description": "Own end-to-end product design.", "location": "Mumbai", "salary_range": "₹12-22 LPA", "skills_required": ["Figma", "UI/UX"], "bulk_openings": 1},
        ]
        for sj in sample_jobs:
            await db.jobs.insert_one({
                "id": new_id(),
                "employer_id": emp["id"],
                "employer_name": emp.get("profile", {}).get("company_name", "Acme Tech"),
                **sj,
                "status": "open",
                "created_at": now_iso(),
            })
        logger.info("Seeded sample jobs")


# Register router
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db():
    client.close()
