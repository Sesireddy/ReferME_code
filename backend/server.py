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
import re
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
# When TEST_RETURN_OTP=1, expose the generated OTP in the signup/forgot response
# so backend test suites can complete the verify-otp step without a real inbox.
TEST_RETURN_OTP = os.environ.get("TEST_RETURN_OTP", "").strip() in ("1", "true", "yes")

CITY_SYNONYMS = {
    "bangalore": ["bangalore", "bengaluru", "bglr"],
    "bengaluru": ["bengaluru", "bangalore", "bglr"],
    "mumbai": ["mumbai", "bombay"],
    "bombay": ["bombay", "mumbai"],
    "chennai": ["chennai", "madras"],
    "madras": ["madras", "chennai"],
    "calcutta": ["calcutta", "kolkata"],
    "kolkata": ["kolkata", "calcutta"],
    "gurgaon": ["gurgaon", "gurugram"],
    "gurugram": ["gurugram", "gurgaon"],
    "delhi": ["delhi", "new delhi", "ncr"],
    "ncr": ["ncr", "delhi", "new delhi", "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad"],
    "trivandrum": ["trivandrum", "thiruvananthapuram"],
    "thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
}


def expand_city(term: str) -> list[str]:
    """Return a list of regex-safe synonyms for a city term. Always includes the original term."""
    if not term:
        return []
    key = term.strip().lower()
    return CITY_SYNONYMS.get(key, [key])


# Business rules
ACTION_COST = 49  # credits per action (apply / book)
INTERVIEW_PRO_REWARD = 35  # credits awarded to pro for a completed mock interview
JOB_POST_REWARD = 100  # one-time credits awarded when a posted job gets >= JOB_POST_REWARD_MIN_APPS valid applications
JOB_POST_REWARD_MIN_APPS = 4
REFERRAL_HIRED_REWARD = 500
HIRING_REWARD = 1500  # credits awarded to job poster on admin-approved hire
INTERVIEW_MIN_DURATION_MIN = 15  # minimum minutes interview must run before it qualifies for the reward
PAYOUT_MIN = 500
FIRST_DEPOSIT_MIN_INR = 199
FIRST_DEPOSIT_BONUS_CREDITS = 398  # ₹199 → 398 credits
FREE_TIER_ACTIONS = 1  # 1 referral + 1 mock interview free

# Personal email domains NOT allowed for professional signup
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
    "rediffmail.com", "live.com", "icloud.com", "aol.com", "ymail.com",
    "protonmail.com", "proton.me", "msn.com", "googlemail.com",
}

# Application status pipeline
APP_STATUSES = ["applied", "shortlisted", "referred", "awaiting_interview", "interview_scheduled", "hired", "rejected"]

# Slot rules
SLOT_MIN_HOURS = 1
SLOT_MAX_HOURS_PER_DAY = 5
SLOT_MIN_DURATION_MIN = 60  # 1 hour

# Jitsi room base
JITSI_BASE = "https://meet.jit.si"

# Mock revenue per deposit captured for analytics
REVENUE_PER_ACTION_INR = ACTION_COST  # for analytics simplification

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
    out = {
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
    # Professional-only fields surfaced to clients (rating + reviews + counts).
    if u.get("role") == "professional":
        out["rating"] = float(u.get("rating") or 0)
        out["ratings_count"] = int(u.get("ratings_count") or 0)
        out["interviews_conducted"] = int(u.get("interviews_conducted") or 0)
        out["referrals_made"] = int(u.get("referrals_made") or 0)
        out["successful_referrals"] = int(u.get("successful_referrals") or 0)
    return out


async def send_otp_email(email: str, otp: str, purpose: str) -> bool:
    """Send OTP email via SendGrid, fall back to logging in mock mode. Returns True on success."""
    subject = "ReferME Verification Code" if purpose == "verify_email" else "ReferME Password Reset Code"
    html = f"""
        <div style="font-family: -apple-system, system-ui, Arial; max-width: 480px; margin: 0 auto; padding: 24px; background: #FDFBF7;">
          <h1 style="color:#FF5A5F; margin: 0 0 12px;">ReferME</h1>
          <p style="font-size:16px; color:#1A1A1A;">Your verification code is:</p>
          <div style="font-size:36px; font-weight:800; letter-spacing:6px; color:#1A1A1A; margin: 16px 0; padding: 16px; background:#fff; border-radius:12px; text-align:center;">{otp}</div>
          <p style="color:#6B7280; font-size:14px;">This code expires in 10 minutes. If you didn't request it, just ignore this email.</p>
        </div>
    """
    return await send_html_email(email, subject, html, mock_purpose=purpose, fallback_text=f"Your OTP is {otp}")


async def send_html_email(to_email: str, subject: str, html: str, mock_purpose: str = "", fallback_text: str = "") -> bool:
    if MOCK_OTP_MODE:
        logger.info("[MOCK-EMAIL] to=%s purpose=%s subject=%s", to_email, mock_purpose, subject)
        return False  # treated as not sent → caller may include OTP in response
    try:
        from sendgrid import SendGridAPIClient  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        msg = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html or fallback_text,
        )
        resp = SendGridAPIClient(SENDGRID_API_KEY).send(msg)
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.warning("SendGrid send failed (%s): %s", subject, e)
        return False


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
    phone: Optional[str] = None
    # student / job-seeker
    gender: Optional[Literal["male", "female", "other", "prefer_not_to_say"]] = None
    education: Optional[str] = None  # one of EDUCATION_OPTIONS values or "__OTHER__"
    education_details: Optional[str] = None  # when education == "__OTHER__" or extra detail
    passed_out_year: Optional[int] = None
    current_location: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
    preferred_role: Optional[Literal["fresher", "experienced", "intern"]] = None
    years_of_experience: Optional[int] = None  # required when experienced; 0 allowed
    currently_working: Optional[Literal["yes", "no"]] = None
    working_since_from_year: Optional[str] = None  # "2010" - "2030"
    working_since_from_month: Optional[str] = None  # "01" - "12"
    working_since_to_year: Optional[str] = None  # null when currently_working = yes (Present)
    working_since_to_month: Optional[str] = None
    notice_period: Optional[str] = None  # 15d_or_less | 1m | 2m | 3m | serving
    annual_salary: Optional[str] = None  # CTC range string e.g. "3-6 LPA"
    skills: Optional[list[str]] = None
    resume_base64: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_size: Optional[int] = None
    resume_mime_type: Optional[str] = None  # "application/pdf" | "application/msword" | "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    resume_link: Optional[str] = None  # external URL alternative
    profile_photo_base64: Optional[str] = None
    certifications: Optional[list[dict]] = None  # [{title, issuer, year, link?}]
    projects: Optional[list[dict]] = None  # [{title, description, link?, tech?}]
    # professional
    company: Optional[str] = None
    designation: Optional[str] = None
    experience_years: Optional[int] = None
    expertise: Optional[list[str]] = None
    alternate_gmail: Optional[str] = None  # personal gmail (optional). Used for Mock Interview meeting invites.
    # employer
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_size: Optional[str] = None
    company_logo_base64: Optional[str] = None
    bio: Optional[str] = None


class GmailVerifyBody(BaseModel):
    email: str
    otp: Optional[str] = None  # supplied on the verify step


class InterviewSlotBody(BaseModel):
    start_at: str  # ISO (any tz, treat as IST if naive)
    end_at: str
    skill_set: Optional[list[str]] = []
    experience_years: Optional[int] = 0  # years of experience required from the candidate
    topic: Optional[str] = ""


class DepositBody(BaseModel):
    amount_inr: int = Field(ge=1)


class VerifyPaymentBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class BookInterviewBody(BaseModel):
    slot_id: str


OPEN_POSITIONS_OPTIONS = ["1 to 5", "1 to 10", "1 to 50", "1 to 100", "100+"]


class JobPostBody(BaseModel):
    title: Optional[str] = ""
    company: Optional[str] = None  # company name (auto-fallback to poster's company)
    description: Optional[str] = ""
    location: Optional[str] = ""
    salary_range: Optional[str] = ""
    skills_required: Optional[list[str]] = None
    category: Literal["fresher", "experienced"] = "fresher"
    experience_required: Optional[int] = 0  # years required if experienced
    open_positions: Optional[int] = None  # numeric (legacy)
    open_positions_label: Optional[Literal["1 to 5", "1 to 10", "1 to 50", "1 to 100", "100+"]] = "1 to 5"
    bulk_openings: Optional[int] = None  # backward compat alias


class JobPatchBody(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    skills_required: Optional[list[str]] = None
    category: Optional[Literal["fresher", "experienced"]] = None
    experience_required: Optional[int] = None
    open_positions: Optional[int] = None
    open_positions_label: Optional[Literal["1 to 5", "1 to 10", "1 to 50", "1 to 100", "100+"]] = None


class ApplyJobBody(BaseModel):
    job_id: str


class StatusUpdateBody(BaseModel):
    application_id: str
    new_status: Literal["shortlisted", "referred", "awaiting_interview", "interview_scheduled", "hired", "rejected"]
    proof_base64: Optional[str] = None
    proof_filename: Optional[str] = None
    proof_mime_type: Optional[str] = None
    note: Optional[str] = ""


class AdminStatusActionBody(BaseModel):
    change_id: str
    action: Literal["approve", "reject"]
    note: Optional[str] = ""


class ReferBody(BaseModel):
    student_id: str
    job_id: str
    note: Optional[str] = ""


class HireBody(BaseModel):
    application_id: str
    proof_base64: Optional[str] = None
    proof_filename: Optional[str] = None
    proof_mime_type: Optional[str] = None
    note: Optional[str] = ""


class CompleteInterviewBody(BaseModel):
    rating: int = Field(ge=1, le=10)
    feedback: Optional[str] = ""


class ReferOwnJobBody(BaseModel):
    application_id: str
    note: Optional[str] = ""


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
    user_doc = {
        "id": new_id(),
        "email": email_lower,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "name": body.name or "",
        "is_email_verified": False,
        "account_status": "active",  # active | suspended
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
        resp["mock_otp"] = otp_code  # included when send failed (e.g., unverified sender) for test continuity
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
    if u.get("account_status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended. Please contact support.")
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
        sent = await send_otp_email(body.email.lower(), otp_code, "reset_password")
        resp = {"message": "If account exists, OTP has been sent."}
        if MOCK_OTP_MODE or not sent or TEST_RETURN_OTP:
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
    out = {"user": user_public(u), "profile": u.get("profile", {})}
    if u["role"] == "professional":
        out["profile_completion"] = compute_pro_profile_completion(u)
        out["missing_fields"] = pro_missing_fields(u)
        out["user"]["gmail_verified"] = bool(u.get("gmail_verified"))
        out["user"]["alternate_gmail"] = u.get("alternate_gmail") or (u.get("profile", {}) or {}).get("alternate_gmail")
        out["user"]["email_verified"] = True  # company email verified at signup
    return out


@api.post("/pro/gmail/send-otp")
async def pro_gmail_send_otp(body: GmailVerifyBody, u: dict = Depends(require_role(["professional"]))):
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    # Only allow personal email providers here (not the corporate domain already used for login).
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


@api.post("/pro/gmail/verify-otp")
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


STUDENT_PROFILE_FIELDS_END = True  # marker



STUDENT_PROFILE_FIELDS = [
    "phone", "gender", "education", "education_details", "passed_out_year", "current_location",
    "dob", "preferred_role", "years_of_experience", "skills",
    "company", "designation", "currently_working",
    "working_since_from_year", "working_since_from_month",
    "working_since_to_year", "working_since_to_month",
    "notice_period", "annual_salary",
    "resume_base64", "resume_filename", "resume_size", "resume_mime_type", "resume_link",
    "profile_photo_base64", "certifications", "projects",
]
PRO_PROFILE_FIELDS = [
    "phone", "company", "designation", "experience_years", "expertise",
    "current_location", "skills", "profile_photo_base64", "alternate_gmail",
]
EMPLOYER_PROFILE_FIELDS = ["company_name", "company_website", "company_size", "company_logo_base64", "bio"]


def compute_pro_profile_completion(user: dict) -> int:
    """Working professional profile completion percentage based on 10 mandatory factors."""
    return 100 - int(round(len(pro_missing_fields(user)) / 10 * 100))


def pro_missing_fields(user: dict) -> list[str]:
    """Returns the list of mandatory profile fields a pro hasn't filled in.
    Drives the 'Profile Incomplete - please complete: …' panel.
    """
    p = user.get("profile") or {}
    missing: list[str] = []
    if not (user.get("name") or "").strip():
        missing.append("Full Name")
    if not (p.get("phone") or "").strip():
        missing.append("Mobile Number")
    if not (user.get("email") or "").strip():
        missing.append("Company Email Address")
    if not (user.get("gmail_verified") and user.get("alternate_gmail")):
        missing.append("Alternate Gmail Address")
    if not (p.get("company") or "").strip():
        missing.append("Company Name")
    if not (p.get("designation") or "").strip():
        missing.append("Designation")
    if not (p.get("experience_years") or p.get("years_of_experience")):
        missing.append("Total Experience")
    if not (p.get("current_location") or "").strip():
        missing.append("Current Location")
    if not ((p.get("skills") or []) or (p.get("expertise") or [])):
        missing.append("Skill Set")
    if not (p.get("profile_photo_base64") or "").strip():
        missing.append("Profile Photo")
    return missing


def compute_resume_score(user: dict) -> int:
    """Resume score 50-100 (0 if no resume). Driven by profile completeness, skills,
    certifications, resume size, and mock interviews attended.

    Range:
      - 0          → no resume uploaded / linked
      - 50-65      → basic profile + resume
      - 66-80      → good profile completion
      - 81-90      → strong profile (projects / certifications)
      - 91-100     → fully completed professional profile
    """
    profile = user.get("profile", {}) or {}
    has_resume = bool(profile.get("resume_base64") or profile.get("resume_link"))
    if not has_resume:
        return 0
    score = 50  # base floor when resume present
    # Identity & contact (max +6)
    if user.get("name"):
        score += 2
    if user.get("email"):
        score += 1
    if profile.get("phone"):
        score += 3
    # Education & timeline (max +6)
    if profile.get("education"):
        score += 3
    if profile.get("passed_out_year"):
        score += 2
    if profile.get("dob"):
        score += 1
    # Location & role preference (max +4)
    if profile.get("current_location"):
        score += 2
    if profile.get("preferred_role"):
        score += 2
    # Skills — each skill +2, capped at 10 (5 skills)
    skills = profile.get("skills", []) or []
    score += min(len(skills) * 2, 10)
    # Resume file size — bigger content → more substance
    rsize = int(profile.get("resume_size") or 0)
    if rsize > 80_000:
        score += 5
    elif rsize > 30_000:
        score += 3
    elif rsize > 5_000:
        score += 1
    # Profile photo bonus
    if profile.get("profile_photo") or profile.get("profile_photo_base64"):
        score += 3
    # Projects / portfolio bonus
    projects = profile.get("projects", []) or []
    if projects:
        score += min(len(projects) * 2, 6)
    # Certifications — each +3, capped at +9
    certs = profile.get("certifications", []) or []
    score += min(len(certs) * 3, 9)
    # Experience field for "experienced" preferred role
    if profile.get("preferred_role") == "experienced" and (profile.get("years_of_experience") or 0) > 0:
        score += 3
    # Mock interviews attended — +2 each up to +20
    attended = int(user.get("interviews_attended") or 0)
    score += min(attended * 2, 20)
    return max(50, min(100, int(score)))


def is_student_complete(profile: dict) -> bool:
    # Always-required: phone, gender, dob, education, passed_out_year, current_location,
    # preferred_role, skills + resume.
    required_common = [
        "phone", "gender", "dob", "education", "passed_out_year",
        "current_location", "preferred_role", "skills",
    ]
    has_resume = bool(profile.get("resume_base64") or profile.get("resume_link"))
    if not has_resume:
        return False
    for r in required_common:
        v = profile.get(r)
        if v is None or v == "" or v == []:
            return False
    if profile.get("education") == "__OTHER__" and not profile.get("education_details"):
        return False

    pref = profile.get("preferred_role")
    # Experienced career details are mandatory only when preferred_role == "experienced".
    if pref == "experienced":
        # years_of_experience must be numeric (0 allowed but discouraged for "experienced")
        yoe = profile.get("years_of_experience")
        if yoe is None:
            return False
        try:
            int(yoe)
        except (TypeError, ValueError):
            return False
        for k in ("company", "designation", "currently_working",
                  "working_since_from_year", "working_since_from_month",
                  "annual_salary"):
            v = profile.get(k)
            if v is None or v == "":
                return False
        cw = profile.get("currently_working")
        if cw == "yes":
            if not profile.get("notice_period"):
                return False
        elif cw == "no":
            if not profile.get("working_since_to_year") or not profile.get("working_since_to_month"):
                return False
        else:
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
        import hashlib
        import hmac
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
async def list_professionals(
    skill: Optional[str] = Query(None, description="Case-insensitive partial match across expertise"),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="fresher | experienced"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD — show only pros with an available slot starting that day"),
    has_available_slots: bool = Query(True, description="Hide pros with no future, available slot"),
    u: dict = Depends(current_user),
):
    pros = await db.users.find({"role": "professional", "profile_complete": True}, {"_id": 0, "password_hash": 0}).to_list(500)
    # Apply skill/location filters with partial, case-insensitive matching.
    if skill:
        sk = skill.lower().strip()
        pros = [
            p for p in pros
            if any(sk in (s or "").lower() for s in (p.get("profile", {}).get("expertise", []) or p.get("profile", {}).get("skills", []) or []))
        ]
    if location:
        loc = location.lower().strip()
        pros = [
            p for p in pros
            if loc in (p.get("profile", {}).get("current_location") or "").lower()
        ]
    if category in ("fresher", "experienced"):
        def _cat(p):
            y = int(p.get("profile", {}).get("experience_years") or 0)
            return "experienced" if y > 0 else "fresher"
        pros = [p for p in pros if _cat(p) == category]

    # Filter to pros with future-available slots (and optional date match) for students.
    if has_available_slots:
        now_dt = datetime.now(timezone.utc)
        slot_q: dict = {"status": "available"}
        slots = await db.interview_slots.find(slot_q, {"_id": 0, "pro_id": 1, "start_at": 1, "skill_set": 1}).to_list(5000)
        pros_with_slots: set = set()
        for s in slots:
            try:
                sd = datetime.fromisoformat((s.get("start_at") or "").replace("Z", "+00:00"))
            except Exception:
                continue
            if sd <= now_dt:
                continue
            if date and sd.strftime("%Y-%m-%d") != date:
                continue
            if skill:
                sk = skill.lower().strip()
                if not any(sk in (x or "").lower() for x in (s.get("skill_set") or [])):
                    # still allow match via pro expertise, so don't strictly exclude
                    pass
            pros_with_slots.add(s["pro_id"])
        pros = [p for p in pros if p["id"] in pros_with_slots]

    return [
        {
            "id": p["id"],
            "name": p.get("name") or p["email"].split("@")[0],
            "company": p.get("profile", {}).get("company"),
            "designation": p.get("profile", {}).get("designation"),
            "experience_years": p.get("profile", {}).get("experience_years"),
            "expertise": p.get("profile", {}).get("expertise") or p.get("profile", {}).get("skills", []),
            "current_location": p.get("profile", {}).get("current_location"),
            "rating": float(p.get("rating") or 0),
            "ratings_count": int(p.get("ratings_count") or 0),
        }
        for p in pros
    ]


@api.post("/interviews/slots")
async def create_slot(body: InterviewSlotBody, u: dict = Depends(require_role(["professional"]))):
    if not u.get("is_email_verified"):
        raise HTTPException(status_code=403, detail="Verify your email before posting interview slots.")
    if not u.get("gmail_verified"):
        raise HTTPException(
            status_code=403,
            detail="Gmail verification is required before creating a Mock Interview slot.",
        )
    if not (body.skill_set or []):
        raise HTTPException(status_code=400, detail="Skill Set is required.")
    try:
        start = datetime.fromisoformat(body.start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(body.end_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    if end <= start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    duration_min = (end - start).total_seconds() / 60
    if duration_min < SLOT_MIN_DURATION_MIN:
        raise HTTPException(status_code=400, detail=f"Slot must be at least {SLOT_MIN_DURATION_MIN} minutes")
    if duration_min > SLOT_MAX_HOURS_PER_DAY * 60:
        raise HTTPException(status_code=400, detail=f"Single slot cannot exceed {SLOT_MAX_HOURS_PER_DAY} hours")
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Slot must be in the future")

    # Daily 5-hour total cap for this pro
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    existing = await db.interview_slots.find(
        {"pro_id": u["id"], "status": {"$in": ["available", "booked"]}},
        {"_id": 0},
    ).to_list(500)
    day_hours = 0.0
    for s in existing:
        try:
            es = datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
            ee = datetime.fromisoformat(s["end_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        # Conflict check
        if start < ee and end > es:
            raise HTTPException(
                status_code=400,
                detail=f"Conflicts with existing slot {es.strftime('%d %b %H:%M')} – {ee.strftime('%H:%M')}",
            )
        # Daily total accumulation
        if day_start <= es < day_end:
            day_hours += (ee - es).total_seconds() / 3600
    if day_hours + duration_min / 60 > SLOT_MAX_HOURS_PER_DAY:
        raise HTTPException(
            status_code=400,
            detail=f"Daily limit {SLOT_MAX_HOURS_PER_DAY}h exceeded (already booked {day_hours:.1f}h on this day).",
        )

    slot_id = new_id()
    meeting_url = f"{JITSI_BASE}/ReferME-{slot_id.split('-')[0]}"
    slot = {
        "id": slot_id,
        "pro_id": u["id"],
        "pro_name": u.get("name") or u["email"].split("@")[0],
        "start_at": body.start_at,
        "end_at": body.end_at,
        "scheduled_at": body.start_at,  # legacy alias
        "skill_set": body.skill_set or [],
        "experience_years": body.experience_years or 0,
        "topic": body.topic or "",
        "status": "available",
        "student_id": None,
        "student_name": None,
        "meeting_url": meeting_url,
        "created_at": now_iso(),
    }
    await db.interview_slots.insert_one(slot)
    return {k: v for k, v in slot.items() if k != "_id"}


@api.get("/interviews/slots")
async def list_slots(
    pro_id: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    date: Optional[str] = Query(None),  # YYYY-MM-DD — only slots starting on this date
    category: Optional[str] = Query(None),  # fresher | experienced
    u: dict = Depends(current_user),
):
    q: dict = {}
    if pro_id:
        q["pro_id"] = pro_id
    if u["role"] == "professional":
        q["pro_id"] = u["id"]
    elif u["role"] == "student" and not pro_id:
        q["status"] = "available"
    if skill:
        q["skill_set"] = {"$regex": skill, "$options": "i"}
    slots = await db.interview_slots.find(q, {"_id": 0}).sort("start_at", 1).to_list(500)
    # Apply date / category / future-only filters (students never see expired or non-future)
    out = []
    now_dt = datetime.now(timezone.utc)
    for s in slots:
        try:
            sd = datetime.fromisoformat((s.get("start_at") or s.get("scheduled_at") or "").replace("Z", "+00:00"))
        except Exception:
            sd = None
        # Students: only future + available
        if u["role"] == "student":
            if not sd or sd <= now_dt:
                continue
            if s.get("status") != "available":
                continue
        if date and sd:
            if sd.strftime("%Y-%m-%d") != date:
                continue
        if category in ("fresher", "experienced"):
            slot_cat = "experienced" if int(s.get("experience_years") or 0) > 0 else "fresher"
            if slot_cat != category:
                continue
        out.append(s)
    return out


def _can_use_free(u: dict, kind: str) -> bool:
    return u.get("free_uses_left", 0) > 0


@api.post("/interviews/book")
async def book_interview(body: BookInterviewBody, u: dict = Depends(require_role(["student"]))):
    slot = await db.interview_slots.find_one({"id": body.slot_id}, {"_id": 0})
    if not slot or slot["status"] != "available":
        raise HTTPException(status_code=400, detail="Slot not available")
    use_free = _can_use_free(u, "interview")
    if not use_free and u.get("credits", 0) < ACTION_COST:
        raise HTTPException(status_code=400, detail="Insufficient credits. Please add credits to continue booking this interview.")
    if use_free:
        await db.users.update_one({"id": u["id"]}, {"$inc": {"free_uses_left": -1}})
    else:
        await _credit_user(u["id"], -ACTION_COST, "interview_booking", {"slot_id": slot["id"]})
    await db.interview_slots.update_one(
        {"id": slot["id"]},
        {"$set": {"status": "booked", "student_id": u["id"], "student_name": u.get("name") or u["email"].split("@")[0], "booked_at": now_iso()}},
    )
    pro = await db.users.find_one({"id": slot["pro_id"]}, {"_id": 0, "password_hash": 0})
    when = slot.get("start_at", "")
    end_when = slot.get("end_at", "")
    # In-app notifications
    await push_notification(u["id"], "Interview booked ✅", f"With {slot['pro_name']} at {when}", "success")
    await push_notification(slot["pro_id"], "New interview booked", f"Student booked your slot at {when}", "info")
    # Email both parties
    meeting = slot.get("meeting_url", "")
    student_html = f"""
        <div style="font-family:-apple-system,Arial; max-width:520px; margin:0 auto; padding:24px; background:#FDFBF7;">
          <h2 style="color:#FF5A5F">Interview confirmed 🎉</h2>
          <p>You're booked with <b>{slot['pro_name']}</b>.</p>
          <ul>
            <li><b>Date / Time:</b> {when} – {end_when}</li>
            <li><b>Topic:</b> {slot.get('topic') or '—'}</li>
            <li><b>Skill set:</b> {', '.join(slot.get('skill_set', []) or []) or '—'}</li>
            <li><b>Meeting link:</b> <a href="{meeting}">{meeting}</a></li>
          </ul>
          <p>Good luck!</p>
        </div>
    """
    pro_html = f"""
        <div style="font-family:-apple-system,Arial; max-width:520px; margin:0 auto; padding:24px; background:#FDFBF7;">
          <h2 style="color:#7C3AED">New interview booked</h2>
          <p><b>Candidate:</b> {u.get('name') or u['email']}</p>
          <p><b>Date / Time:</b> {when} – {end_when}</p>
          <p><b>Topic:</b> {slot.get('topic') or '—'}</p>
          <p><b>Meeting link:</b> <a href="{meeting}">{meeting}</a></p>
        </div>
    """
    await send_html_email(u["email"], "ReferME · Interview confirmed", student_html, mock_purpose="booking_student")
    if pro and pro.get("email"):
        await send_html_email(pro["email"], "ReferME · New interview booking", pro_html, mock_purpose="booking_pro")
    return {"message": "Booked", "used_free": use_free, "meeting_url": meeting}


@api.get("/interviews/my-bookings")
async def my_bookings(
    upcoming_only: bool = Query(True),
    u: dict = Depends(current_user),
):
    """Return slots the current user has booked (student) or is conducting (pro).
    Used by dashboards to surface 'Join video' CTAs for upcoming sessions.
    """
    if u["role"] == "student":
        q = {"student_id": u["id"]}
    elif u["role"] == "professional":
        q = {"pro_id": u["id"], "student_id": {"$ne": None}}
    else:
        return []
    slots = await db.interview_slots.find(q, {"_id": 0}).sort("start_at", 1).to_list(500)
    now_dt = datetime.now(timezone.utc)
    out = []
    for s in slots:
        try:
            sd = datetime.fromisoformat((s.get("start_at") or "").replace("Z", "+00:00"))
            ed = datetime.fromisoformat((s.get("end_at") or "").replace("Z", "+00:00"))
        except Exception:
            sd, ed = None, None
        # Only consider booked or completed within last 24h
        if upcoming_only:
            if s.get("status") in ("cancelled",):
                continue
            if ed and ed < now_dt - timedelta(hours=2):
                continue
        # Hydrate with counterparty name
        if u["role"] == "student":
            s["counterparty_name"] = s.get("pro_name")
        else:
            s["counterparty_name"] = s.get("student_name")
        # Join window: enabled 10 min before start until 2h after end
        s["join_enabled"] = False
        if sd and ed:
            window_start = sd - timedelta(minutes=10)
            window_end = ed + timedelta(hours=2)
            s["join_enabled"] = window_start <= now_dt <= window_end
        out.append(s)
    return out


@api.post("/interviews/{slot_id}/complete")
async def complete_interview(
    slot_id: str,
    body: CompleteInterviewBody,
    u: dict = Depends(require_role(["professional"])),
):
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot or slot["pro_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["status"] != "booked":
        raise HTTPException(status_code=400, detail="Slot not booked")
    if not slot.get("student_id"):
        raise HTTPException(status_code=400, detail="No candidate booked for this slot")
    # Both-joined validation: require both participants to have joined at least once
    joined = slot.get("joined_by") or []
    if slot["pro_id"] not in joined or slot["student_id"] not in joined:
        raise HTTPException(status_code=400, detail="Both participants must join the interview before it can be completed")
    # Minimum duration validation: scheduled slot must have started at least INTERVIEW_MIN_DURATION_MIN ago
    try:
        sd = datetime.fromisoformat((slot.get("start_at") or "").replace("Z", "+00:00"))
    except Exception:
        sd = None
    now_dt = datetime.now(timezone.utc)
    if sd and (now_dt - sd) < timedelta(minutes=INTERVIEW_MIN_DURATION_MIN):
        raise HTTPException(
            status_code=400,
            detail=f"Interview must run for at least {INTERVIEW_MIN_DURATION_MIN} minutes before completion",
        )
    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$set": {
            "status": "completed",
            "completed_at": now_iso(),
            "candidate_rating": body.rating,
            "candidate_feedback": body.feedback or "",
        }},
    )
    # Pro reward
    await _credit_user(u["id"], INTERVIEW_PRO_REWARD, "mock_interview_reward", {
        "slot_id": slot_id,
        "candidate_id": slot["student_id"],
        "rating": body.rating,
    })
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
            f"Your interviewer rated you {body.rating}/10. Resume score: {new_score}/100.",
            "success",
        )
    # Aggregate pro rating: store running average and total ratings count
    pro = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    prev_count = int(pro.get("ratings_count") or 0)
    prev_avg = float(pro.get("rating") or 0)
    new_count = prev_count + 1
    new_avg = round(((prev_avg * prev_count) + body.rating) / new_count, 2)
    await db.users.update_one(
        {"id": u["id"]},
        {
            "$inc": {"interviews_conducted": 1, "ratings_count": 1},
            "$set": {"rating": new_avg},
        },
    )
    await push_notification(
        u["id"],
        f"Earned +{INTERVIEW_PRO_REWARD} credits 🎯",
        f"Interview marked completed. Your rating: {new_avg}/10 ({new_count} interviews).",
        "success",
    )
    return {"message": "Completed", "earned": INTERVIEW_PRO_REWARD, "pro_rating": new_avg, "candidate_rating": body.rating}


@api.post("/interviews/{slot_id}/joined")
async def mark_interview_joined(slot_id: str, u: dict = Depends(current_user)):
    """Frontend hits this when the user actually opens the Jitsi room.
    Used by complete_interview to verify both parties showed up.
    """
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if u["id"] not in (slot["pro_id"], slot.get("student_id")):
        raise HTTPException(status_code=403, detail="Not your session")
    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$addToSet": {"joined_by": u["id"]}},
    )
    return {"message": "Joined"}


# ------------------- Jobs & Applications & Referrals -------------------
@api.post("/jobs")
async def post_job(body: JobPostBody, u: dict = Depends(require_role(["employer", "professional"]))):
    # Mandatory-field guards (Pydantic validates length, but emit human messages for the UI).
    if not body.title or len(body.title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job Title is required.")
    if not body.description or len(body.description.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job Description is required.")
    if not body.location or len(body.location.strip()) < 2:
        raise HTTPException(status_code=400, detail="Location is required.")
    if not body.skills_required or len([s for s in body.skills_required if s.strip()]) == 0:
        raise HTTPException(status_code=400, detail="Skill Set is required.")
    profile = u.get("profile", {}) or {}
    default_company = profile.get("company_name") or profile.get("company")
    company_resolved = (body.company or default_company or "").strip()
    if not company_resolved:
        raise HTTPException(status_code=400, detail="Company Name is required.")
    # Numeric open_positions for back-compat; canonical display uses open_positions_label.
    label = body.open_positions_label or "1 to 5"
    LABEL_NUMERIC = {"1 to 5": 5, "1 to 10": 10, "1 to 50": 50, "1 to 100": 100, "100+": 100}
    openings = body.open_positions or LABEL_NUMERIC.get(label, 5)
    category = body.category or ("experienced" if (body.experience_required or 0) > 0 else "fresher")
    exp_req = body.experience_required or 0
    if category == "experienced" and exp_req <= 0:
        raise HTTPException(status_code=400, detail="experience_required must be > 0 for experienced category")
    job = {
        "id": new_id(),
        "employer_id": u["id"],
        "employer_name": company_resolved,
        "posted_by_role": u["role"],
        "posted_by_name": u.get("name") or u["email"].split("@")[0],
        "title": body.title.strip(),
        "company": company_resolved,
        "description": body.description.strip(),
        "location": body.location.strip(),
        "salary_range": body.salary_range or "",
        "skills_required": [s.strip() for s in body.skills_required if s.strip()],
        "category": category,
        "experience_required": exp_req,
        "open_positions": openings,
        "open_positions_label": label,
        "bulk_openings": openings,  # back-compat
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.jobs.insert_one(job)
    return {k: v for k, v in job.items() if k != "_id"}


@api.get("/jobs")
async def list_jobs(
    u: dict = Depends(current_user),
    skill: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    exp_min: Optional[int] = Query(None),
    exp_max: Optional[int] = Query(None),
    company: Optional[str] = Query(None),
    mine: bool = Query(False, description="When true (pro/employer), return only jobs posted by the current user"),
):
    q: dict = {}
    if u["role"] == "employer":
        q["employer_id"] = u["id"]
    elif u["role"] == "professional":
        if mine:
            q["employer_id"] = u["id"]
        else:
            # Pros see: their own posts + open jobs posted by employers.
            # Jobs posted by OTHER pros are intentionally hidden so referrals stay scoped to the posting pro.
            q["$or"] = [
                {"employer_id": u["id"]},
                {"status": "open", "posted_by_role": {"$ne": "professional"}},
            ]
    else:
        # students & admin
        q["status"] = "open"
    if skill:
        # Partial, case-insensitive match. e.g. "Java" matches "Core Java", "Java Full Stack".
        q["skills_required"] = {"$regex": re.escape(skill), "$options": "i"}
    if location:
        # Friendly partial match + city synonyms (Bangalore ↔ Bengaluru, Mumbai ↔ Bombay, etc.)
        synonyms = expand_city(location)
        pattern = "|".join(re.escape(s) for s in synonyms)
        q["location"] = {"$regex": pattern, "$options": "i"}
    if category in ("fresher", "experienced"):
        q["category"] = category
    if company:
        q["company"] = {"$regex": company, "$options": "i"}
    if exp_min is not None:
        q["experience_required"] = {**(q.get("experience_required") or {}), "$gte": int(exp_min)}
    if exp_max is not None:
        q["experience_required"] = {**(q.get("experience_required") or {}), "$lte": int(exp_max)}
    jobs = await db.jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    # Annotate `applied` flag for students
    if u["role"] == "student" and jobs:
        my_apps = await db.applications.find({"student_id": u["id"]}, {"_id": 0, "job_id": 1, "status": 1}).to_list(1000)
        by_job = {a["job_id"]: a["status"] for a in my_apps}
        for j in jobs:
            j["applied"] = j["id"] in by_job
            j["application_status"] = by_job.get(j["id"])
    # Annotate application count + reward status for employer/pro on their own jobs
    if u["role"] in ("employer", "professional"):
        own_ids = [j["id"] for j in jobs if j.get("employer_id") == u["id"]]
        if own_ids:
            agg = await db.applications.aggregate([
                {"$match": {"job_id": {"$in": own_ids}, "status": {"$nin": ["withdrawn"]}}},
                {"$group": {"_id": "$job_id", "n": {"$sum": 1}}},
            ]).to_list(1000)
            counts = {r["_id"]: r["n"] for r in agg}
            for j in jobs:
                if j.get("employer_id") == u["id"]:
                    j["applications_count"] = counts.get(j["id"], 0)
    return jobs


@api.get("/jobs/{job_id}")
async def get_job(job_id: str, u: dict = Depends(current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] == "student":
        app = await db.applications.find_one({"student_id": u["id"], "job_id": job_id}, {"_id": 0})
        job["applied"] = bool(app)
        job["application_status"] = app["status"] if app else None
    return job


@api.patch("/jobs/{job_id}")
async def edit_job(job_id: str, body: JobPatchBody, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can edit")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "open_positions" in updates:
        updates["bulk_openings"] = updates["open_positions"]
    updates["updated_at"] = now_iso()
    await db.jobs.update_one({"id": job_id}, {"$set": updates})
    out = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return out


@api.post("/jobs/{job_id}/close")
async def close_job(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can close")
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "closed", "updated_at": now_iso()}})
    return {"message": "Closed"}


@api.post("/jobs/{job_id}/reopen")
async def reopen_job(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can reopen")
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "open", "updated_at": now_iso()}})
    return {"message": "Reopened"}


@api.get("/jobs/{job_id}/applicants")
async def job_applicants(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can view")
    apps = await db.applications.find({"job_id": job_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    student_ids = [a["student_id"] for a in apps]
    students = await db.users.find({"id": {"$in": student_ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    sm = {s["id"]: s for s in students}
    out = []
    for a in apps:
        s = sm.get(a["student_id"], {})
        p = s.get("profile", {}) or {}
        out.append({
            **a,
            "student_profile": {
                "name": s.get("name") or s.get("email", "").split("@")[0],
                "skills": p.get("skills", []),
                "resume_score": p.get("resume_score", 0),
                "current_location": p.get("current_location"),
                "preferred_role": p.get("preferred_role"),
                "years_of_experience": p.get("years_of_experience"),
                "education": p.get("education"),
                "passed_out_year": p.get("passed_out_year"),
            },
        })
    return out


@api.post("/jobs/{job_id}/save")
async def save_job(job_id: str, u: dict = Depends(require_role(["student"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    res = await db.saved_jobs.update_one(
        {"student_id": u["id"], "job_id": job_id},
        {"$setOnInsert": {"id": new_id(), "student_id": u["id"], "job_id": job_id, "saved_at": now_iso()}},
        upsert=True,
    )
    return {"saved": True, "first_time": res.upserted_id is not None}


@api.delete("/jobs/{job_id}/save")
async def unsave_job(job_id: str, u: dict = Depends(require_role(["student"]))):
    await db.saved_jobs.delete_one({"student_id": u["id"], "job_id": job_id})
    return {"saved": False}


@api.get("/saved-jobs")
async def list_saved_jobs(u: dict = Depends(require_role(["student"]))):
    saved = await db.saved_jobs.find({"student_id": u["id"]}, {"_id": 0}).sort("saved_at", -1).to_list(500)
    job_ids = [s["job_id"] for s in saved]
    jobs = await db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0}).to_list(500)
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
        raise HTTPException(status_code=402, detail="Insufficient credits. Please add credits to continue applying for this job.")
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
        "status": "applied",  # applied -> shortlisted -> referred -> awaiting_interview -> interview_scheduled -> hired / rejected
        "status_history": [{"status": "applied", "at": now_iso(), "by": u["id"]}],
        "created_at": now_iso(),
    }
    await db.applications.insert_one(app_doc)
    await push_notification(u["id"], "Application sent ✉️", f"Applied to {job['title']}", "success")
    await push_notification(job["employer_id"], "New applicant", f"For {job['title']}", "info")

    # Pro-poster reward: when the job (posted by a professional) reaches >= JOB_POST_REWARD_MIN_APPS valid
    # non-withdrawn applications, the poster receives a one-time JOB_POST_REWARD credit bonus.
    # We use a conditional update + modified_count check to make crediting race-safe under concurrent applies.
    if job.get("posted_by_role") == "professional" and not job.get("posting_reward_paid"):
        valid_count = await db.applications.count_documents({
            "job_id": job["id"],
            "status": {"$nin": ["withdrawn"]},
        })
        if valid_count >= JOB_POST_REWARD_MIN_APPS:
            res = await db.jobs.update_one(
                {"id": job["id"], "posting_reward_paid": {"$ne": True}},
                {"$set": {"posting_reward_paid": True}},
            )
            if res.modified_count == 1:
                await _credit_user(
                    job["employer_id"],
                    JOB_POST_REWARD,
                    "job_post_reward",
                    {"job_id": job["id"], "job_title": job.get("title"), "applications": valid_count},
                )
                await push_notification(
                    job["employer_id"],
                    f"Earned +{JOB_POST_REWARD} credits 💼",
                    f"Your post '{job.get('title')}' crossed {JOB_POST_REWARD_MIN_APPS} applications!",
                    "success",
                )

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
async def hire_candidate(body: HireBody, u: dict = Depends(require_role(["employer", "professional"]))):
    """Mark a candidate as hired. This goes into 'hired_pending' status until admin approves
    and the +HIRING_REWARD credits go to the job poster after admin approval.
    Pros can only hire candidates from jobs THEY posted.
    """
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    if appdoc["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only the job poster can mark this candidate hired")
    if appdoc["status"] in ("hired", "hired_pending"):
        raise HTTPException(status_code=400, detail="Already submitted for hire approval")
    # Require proof screenshot for the hiring reward
    if not body.proof_base64 and not body.note:
        raise HTTPException(status_code=400, detail="Please attach supporting evidence or a note")
    change = {
        "id": new_id(),
        "application_id": body.application_id,
        "requested_by_id": u["id"],
        "requested_by_role": u["role"],
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": "hired",
        "proof_base64": body.proof_base64,
        "proof_filename": body.proof_filename,
        "proof_mime_type": body.proof_mime_type,
        "note": body.note or "",
        "status": "pending",
        "admin_note": "",
        "created_at": now_iso(),
    }
    await db.status_changes.insert_one(change)
    await db.applications.update_one(
        {"id": body.application_id},
        {"$set": {"status": "hired_pending", "hired_pending_at": now_iso()}},
    )
    await push_notification(u["id"], "Hire submitted for admin review ⏳", "We'll credit you 1500 once approved.", "info")
    await push_notification(appdoc["student_id"], "Hire submitted 🎉", f"For {appdoc['job_title']} — pending admin verification.", "info")
    return {"message": "Submitted for admin verification", "change_id": change["id"]}


@api.post("/applications/refer-own")
async def refer_own_applicant(body: ReferOwnJobBody, u: dict = Depends(require_role(["professional"]))):
    """The pro who posted the job can refer an applicant directly from their My Posted Jobs.
    Status pipeline: applied → shortlisted → referred (in one shot, with history).
    """
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    job = await db.jobs.find_one({"id": appdoc["job_id"]}, {"_id": 0})
    if not job or job.get("employer_id") != u["id"] or job.get("posted_by_role") != "professional":
        raise HTTPException(status_code=403, detail="Only the posting professional can refer this candidate")
    if appdoc["status"] in ("referred", "hired", "hired_pending"):
        return {"message": "Already referred", "status": appdoc["status"]}
    hist = list(appdoc.get("status_history") or [])
    for st in ("shortlisted", "referred"):
        hist.append({"status": st, "at": now_iso(), "by": u["id"], "note": body.note or ""})
    await db.applications.update_one(
        {"id": appdoc["id"]},
        {"$set": {
            "status": "referred",
            "status_history": hist,
            "referrer_pro_id": u["id"],
            "referrer_pro_name": u.get("name") or u["email"].split("@")[0],
            "referral_note": body.note or "",
        }},
    )
    await db.users.update_one({"id": u["id"]}, {"$inc": {"referrals_made": 1}})
    await push_notification(appdoc["student_id"], "You've been referred 🌟", f"For {appdoc['job_title']}", "success")
    await push_notification(u["id"], "Referral submitted ✅", f"For {appdoc['job_title']}", "success")
    # Admin gets a heads-up too via status_changes log (best-effort)
    await db.status_changes.insert_one({
        "id": new_id(),
        "application_id": appdoc["id"],
        "requested_by_id": u["id"],
        "requested_by_role": "professional",
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": "referred",
        "note": body.note or "",
        "status": "approved",  # auto-approved (pro is the job owner)
        "auto": True,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return {"message": "Referred", "application_id": appdoc["id"]}


# ------------------- Status pipeline (Applied → Hired) -------------------
@api.post("/applications/status")
async def request_status_change(body: StatusUpdateBody, u: dict = Depends(current_user)):
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    # Authorization: student (their own app), employer (their job), pro (referrer), admin
    is_owner_student = (u["role"] == "student" and appdoc["student_id"] == u["id"])
    is_employer = (u["role"] == "employer" and appdoc["employer_id"] == u["id"])
    is_referrer = (u["role"] == "professional" and appdoc.get("referrer_pro_id") == u["id"])
    if not (is_owner_student or is_employer or is_referrer or u["role"] == "admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    change = {
        "id": new_id(),
        "application_id": body.application_id,
        "requested_by_id": u["id"],
        "requested_by_role": u["role"],
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": body.new_status,
        "proof_base64": body.proof_base64,
        "proof_filename": body.proof_filename,
        "proof_mime_type": body.proof_mime_type,
        "note": body.note or "",
        "status": "pending",  # pending | approved | rejected
        "admin_note": "",
        "created_at": now_iso(),
    }
    await db.status_changes.insert_one(change)
    await push_notification(u["id"], "Status update submitted", "Pending admin review.", "info")
    return {"message": "Submitted for admin review", "change_id": change["id"], "status": "pending"}


@api.get("/applications/{app_id}/timeline")
async def application_timeline(app_id: str, u: dict = Depends(current_user)):
    appdoc = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    history = appdoc.get("status_history", [])
    pending = await db.status_changes.find(
        {"application_id": app_id, "status": "pending"}, {"_id": 0, "proof_base64": 0}
    ).sort("created_at", -1).to_list(50)
    return {
        "current_status": appdoc["status"],
        "history": history,
        "pending_changes": pending,
    }


@api.get("/admin/status-changes")
async def admin_status_changes(_: dict = Depends(admin_only)):
    items = await db.status_changes.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.post("/admin/status-changes/action")
async def admin_status_action(body: AdminStatusActionBody, _: dict = Depends(admin_only)):
    change = await db.status_changes.find_one({"id": body.change_id}, {"_id": 0})
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    if change["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")
    await db.status_changes.update_one(
        {"id": body.change_id},
        {"$set": {"status": body.action + "d" if body.action == "approve" else "rejected", "admin_note": body.note or "", "updated_at": now_iso()}},
    )
    if body.action == "approve":
        appdoc = await db.applications.find_one({"id": change["application_id"]}, {"_id": 0})
        if appdoc:
            new_hist = (appdoc.get("status_history") or []) + [{
                "status": change["to_status"],
                "at": now_iso(),
                "by": change["requested_by_id"],
                "note": change.get("note") or "",
            }]
            update_fields = {"status": change["to_status"], "status_history": new_hist}
            if change["to_status"] == "hired":
                update_fields["hired_at"] = now_iso()
            await db.applications.update_one({"id": appdoc["id"]}, {"$set": update_fields})
            # Hiring reward → goes to the JOB POSTER (employer/pro who owns the job)
            if change["to_status"] == "hired":
                job_owner_id = appdoc.get("employer_id")
                if job_owner_id:
                    await _credit_user(
                        job_owner_id,
                        HIRING_REWARD,
                        "hiring_reward",
                        {
                            "application_id": appdoc["id"],
                            "candidate_name": appdoc.get("student_name"),
                            "candidate_id": appdoc.get("student_id"),
                            "job_id": appdoc.get("job_id"),
                            "job_title": appdoc.get("job_title"),
                        },
                    )
                    await db.users.update_one({"id": job_owner_id}, {"$inc": {"successful_hires": 1}})
                    await push_notification(
                        job_owner_id,
                        f"Hiring bonus 💸 +{HIRING_REWARD} credits",
                        f"Verified hire of {appdoc.get('student_name')} for {appdoc.get('job_title')}.",
                        "success",
                    )
                # Referrer (separate person from job poster) keeps the smaller referral bonus
                if appdoc.get("referrer_pro_id") and appdoc.get("referrer_pro_id") != job_owner_id:
                    await _credit_user(appdoc["referrer_pro_id"], REFERRAL_HIRED_REWARD, "referral_hired", {"application_id": appdoc["id"]})
                    await db.users.update_one({"id": appdoc["referrer_pro_id"]}, {"$inc": {"successful_referrals": 1}})
                    await push_notification(appdoc["referrer_pro_id"], "Referral bonus 💸", f"+{REFERRAL_HIRED_REWARD} credits — candidate hired!", "success")
            await push_notification(
                appdoc["student_id"],
                "Status updated 📈" if change["to_status"] != "hired" else "You're hired! 🎉",
                f"Your application is now: {change['to_status'].replace('_', ' ').title()}",
                "success",
            )
    else:
        # Rejected — keep status as before
        await push_notification(change["requested_by_id"], "Status update rejected", body.note or "Please attach proof.", "error")
    return {"message": f"Change {body.action}d"}


# ------------------- Leaderboards -------------------
@api.get("/leaderboard/student/me/ranks")
async def my_student_ranks(u: dict = Depends(require_role(["student"]))):
    """Return three independent ranks for the current student:
    - overall_rank: among ALL students (sorted by composite/resume score desc)
    - category_rank: among students in the same category (fresher/experienced)
    - skill_rank: among students who share the user's PRIMARY (first) skill
    Each rank starts at 1. Returns null when the user has no profile data to compare.
    """
    me = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    p = me.get("profile", {}) or {}
    my_score = int(p.get("resume_score") or 0)
    me_year = int(p.get("passed_out_year") or 0)
    me_role = (p.get("preferred_role") or "").lower().strip()
    skills = p.get("skills") or []
    primary_skill = (skills[0] if skills else "").strip()

    # Compute overall: count students with strictly higher score → my position = count+1
    async def _rank_above(filter_q: dict) -> int:
        agg = await db.users.aggregate([
            {"$match": filter_q},
            {"$project": {"score": {"$ifNull": ["$profile.resume_score", 0]}}},
            {"$match": {"score": {"$gt": my_score}}},
            {"$count": "n"},
        ]).to_list(1)
        return (agg[0]["n"] if agg else 0) + 1

    overall_rank = await _rank_above({"role": "student"})
    # Category infer: fresher if no exp, else experienced. Match on preferred_role+passed_out_year proximity.
    cat_filter: dict = {"role": "student"}
    if me_role:
        cat_filter["profile.preferred_role"] = me_role
    elif me_year:
        cat_filter["profile.passed_out_year"] = me_year
    category_rank = await _rank_above(cat_filter) if (me_role or me_year) else None

    skill_rank = None
    if primary_skill:
        skill_filter = {"role": "student", "profile.skills": {"$regex": f"^{re.escape(primary_skill)}$", "$options": "i"}}
        skill_rank = await _rank_above(skill_filter)
    return {
        "overall_rank": overall_rank,
        "category_rank": category_rank,
        "skill_rank": skill_rank,
        "primary_skill": primary_skill or None,
        "category_label": me_role or (str(me_year) if me_year else None),
        "resume_score": my_score,
    }


@api.get("/leaderboard/students")
async def leaderboard_students(
    u: dict = Depends(current_user),
    category: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    min_rating: Optional[float] = Query(None),
    min_interviews: Optional[int] = Query(None),
    min_jobs_applied: Optional[int] = Query(None),
    min_referrals: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    students = await db.users.find({"role": "student"}, {"_id": 0, "password_hash": 0}).to_list(5000)
    out: list[dict] = []
    for s in students:
        sid = s["id"]
        profile = s.get("profile", {}) or {}
        skills = profile.get("skills", []) or []
        cat = profile.get("preferred_role")
        loc = profile.get("current_location")
        score_val = int(profile.get("resume_score") or 0)
        attended = int(s.get("interviews_attended", 0) or 0)
        jobs_applied = await db.applications.count_documents({"student_id": sid})
        referrals_received = await db.applications.count_documents({"student_id": sid, "referrer_pro_id": {"$ne": None}})
        rating = float(profile.get("rating") or 0)
        if category and cat != category:
            continue
        if skill and not any(skill.lower() in (sk or "").lower() for sk in skills):
            continue
        if location and location.lower() not in (loc or "").lower():
            continue
        if min_score is not None and score_val < min_score:
            continue
        if max_score is not None and score_val > max_score:
            continue
        if min_rating is not None and rating < min_rating:
            continue
        if min_interviews is not None and attended < min_interviews:
            continue
        if min_jobs_applied is not None and jobs_applied < min_jobs_applied:
            continue
        if min_referrals is not None and referrals_received < min_referrals:
            continue
        composite = attended * 10 + score_val + jobs_applied * 2 + referrals_received * 5
        out.append({
            "id": sid,
            "name": s.get("name") or s["email"].split("@")[0],
            "category": cat or "—",
            "skills": skills,
            "current_location": loc or "—",
            "resume_score": score_val,
            "interviews_attended": attended,
            "rating": rating,
            "jobs_applied": jobs_applied,
            "referrals_received": referrals_received,
            "composite_score": composite,
            "is_me": sid == u["id"],
        })
    out.sort(key=lambda x: (-x["composite_score"], -x["resume_score"]))
    for i, e in enumerate(out):
        e["rank"] = i + 1
    total = len(out)
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": total, "page": page, "page_size": page_size, "items": out[start:end]}


@api.get("/leaderboard/professionals")
async def leaderboard_pros(u: dict = Depends(current_user)):
    pros = await db.users.find({"role": "professional"}, {"_id": 0, "password_hash": 0}).to_list(1000)
    def score(p: dict) -> int:
        return (
            p.get("interviews_conducted", 0) * 5
            + p.get("referrals_made", 0) * 3
            + p.get("successful_referrals", 0) * 20
            + int(round(float(p.get("rating") or 0) * 4))  # rating weights ~max 40
        )
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
            "rating": float(p.get("rating") or 0),
            "ratings_count": int(p.get("ratings_count") or 0),
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
    return [{**user_public(u), "account_status": u.get("account_status", "active")} for u in users]


@api.post("/admin/users/{user_id}/suspend")
async def admin_suspend(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.update_one({"id": user_id}, {"$set": {"account_status": "suspended"}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Suspended"}


@api.post("/admin/users/{user_id}/activate")
async def admin_activate(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.update_one({"id": user_id}, {"$set": {"account_status": "active"}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Activated"}


@api.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.delete_one({"id": user_id, "role": {"$ne": "admin"}})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="User not found or admin cannot be deleted")
    return {"message": "Deleted"}


@api.get("/admin/jobs")
async def admin_all_jobs(_: dict = Depends(admin_only)):
    return await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.delete("/admin/jobs/{job_id}")
async def admin_delete_job(job_id: str, _: dict = Depends(admin_only)):
    res = await db.jobs.delete_one({"id": job_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job removed"}


@api.get("/admin/interviews")
async def admin_interviews(_: dict = Depends(admin_only)):
    return await db.interview_slots.find({}, {"_id": 0}).sort("start_at", -1).to_list(500)


@api.delete("/admin/interviews/{slot_id}")
async def admin_cancel_slot(slot_id: str, _: dict = Depends(admin_only)):
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    await db.interview_slots.update_one({"id": slot_id}, {"$set": {"status": "cancelled"}})
    if slot.get("student_id"):
        # refund credits
        await _credit_user(slot["student_id"], ACTION_COST, "interview_cancel_refund", {"slot_id": slot_id})
        await push_notification(slot["student_id"], "Interview cancelled", "Credits refunded.", "warning")
    return {"message": "Slot cancelled"}


@api.post("/admin/wallet/refund")
async def admin_refund(user_id: str = Query(...), amount: int = Query(...), reason: str = Query("admin_refund"), _: dict = Depends(admin_only)):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    new_balance = await _credit_user(user_id, amount, reason, {"by": "admin"})
    await push_notification(user_id, "Credit adjustment", f"+{amount} credits applied by admin.", "info")
    return {"credits": new_balance}


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(admin_only)):
    deposits = await db.deposit_orders.find({"status": "paid"}, {"_id": 0, "amount_inr": 1}).to_list(10000)
    revenue = sum(int(d.get("amount_inr", 0)) for d in deposits)
    hires = await db.applications.count_documents({"status": "hired"})
    referrals_done = await db.applications.count_documents({"referrer_pro_id": {"$ne": None}})
    return {
        "total_users": await db.users.count_documents({}),
        "students": await db.users.count_documents({"role": "student"}),
        "professionals": await db.users.count_documents({"role": "professional"}),
        "employers": await db.users.count_documents({"role": "employer"}),
        "active_students": await db.users.count_documents({"role": "student", "account_status": {"$ne": "suspended"}}),
        "active_professionals": await db.users.count_documents({"role": "professional", "account_status": {"$ne": "suspended"}}),
        "jobs": await db.jobs.count_documents({}),
        "jobs_open": await db.jobs.count_documents({"status": "open"}),
        "applications": await db.applications.count_documents({}),
        "referrals_completed": referrals_done,
        "interviews": await db.interview_slots.count_documents({"status": "completed"}),
        "hires": hires,
        "revenue_inr": revenue,
        "payouts_pending": await db.payouts.count_documents({"status": "requested"}),
        "disputes_open": await db.disputes.count_documents({"status": "open"}),
        "status_changes_pending": await db.status_changes.count_documents({"status": "pending"}),
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
