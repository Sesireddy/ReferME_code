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
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "ReferME <noreply@referme.today>").strip()
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@referme.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
EMERGENT_AUTH_URL = os.environ.get(
    "EMERGENT_AUTH_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)

MOCK_OTP_MODE = not (bool(RESEND_API_KEY) or bool(SENDGRID_API_KEY))

# --- Resend rate-limiter (free tier = 2 req/sec) ---
# Serialise Resend sends with a global async lock; keep at least RESEND_MIN_GAP_SECS
# between API calls so back-to-back emails (e.g. student + pro on booking) don't 429.
import asyncio as _asyncio_for_throttle  # noqa: E402
RESEND_MIN_GAP_SECS = float(os.environ.get("RESEND_MIN_GAP_SECS", "0.55"))
_resend_lock = _asyncio_for_throttle.Lock()
_resend_last_sent_monotonic = 0.0
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
# Credit costs are now per Job Seeker category (see get_action_cost()):
#   Fresher / Intern  → 99 credits per action (book interview / apply pro job)
#   Experienced       → 199 credits per action
# Admin Walk-in & Direct Jobs stay FREE (no credit deduction — enforced separately).
ACTION_COST_FRESHER = 99
ACTION_COST_EXPERIENCED = 199
ACTION_COST = ACTION_COST_FRESHER  # legacy default (used for admin refunds when category is unknown)
INTERVIEW_PRO_REWARD = 110  # credits awarded to pro for a completed mock interview
JOB_POST_REWARD = 200  # one-time credits awarded when a posted job gets >= JOB_POST_REWARD_MIN_APPS valid applications
JOB_POST_REWARD_MIN_APPS = 4


def get_action_cost(u: dict) -> int:
    """Credit cost per Job Seeker action based on the profile category.

    - Student with `preferred_role == "experienced"`  → 199
    - Student with `preferred_role in ("fresher","intern")` (or missing) → 99
    - Non-students → 0 (they never pay to book/apply)
    """
    if not u or u.get("role") != "student":
        return 0
    profile = u.get("profile") or {}
    role = (profile.get("preferred_role") or "fresher").strip().lower()
    return ACTION_COST_EXPERIENCED if role == "experienced" else ACTION_COST_FRESHER

# ------------------- Referral Program -------------------
REFERRAL_REWARD = 25  # credits awarded to the referrer for each successful Job Seeker signup


# ------------------- Working Professional Score (WPS) -------------------
def _pro_interview_score(n: int) -> int:
    """Interview Activity Score (0..100) — bucketed by total interviews conducted."""
    if n <= 0:
        return 0
    if n <= 5:
        return 20
    if n <= 20:
        return 40
    if n <= 50:
        return 60
    if n <= 100:
        return 80
    return 100


def _pro_jobs_score(n: int) -> int:
    """Job Posting Activity Score (0..100) — bucketed by total jobs posted."""
    if n <= 0:
        return 0
    if n <= 3:
        return 20
    if n <= 10:
        return 40
    if n <= 25:
        return 60
    if n <= 50:
        return 80
    return 100


def compute_wps(interviews_conducted: int, jobs_posted: int) -> float:
    """Working Professional Score (0-100).

    Formula:
        WPS = (interview_score * 0.60) + (job_score * 0.40)
    """
    ints = _pro_interview_score(int(interviews_conducted or 0))
    jobs = _pro_jobs_score(int(jobs_posted or 0))
    wps = ints * 0.6 + jobs * 0.4
    return round(max(0.0, min(100.0, wps)), 2)

def make_referral_code() -> str:
    """Generate an opaque, human-readable referral code like 'USER12AB34CD'."""
    return "USER" + secrets.token_hex(4).upper()

def referral_link_for(code: str) -> str:
    base = os.environ.get("REFERRAL_BASE_URL", "https://referme.app/invite")
    return f"{base}?ref={code}"
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
SLOT_MIN_DURATION_MIN = 30  # 30 min per sub-slot; sessions must be a multiple of 30 min

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
    # Student-only fields used by dashboard (TPS components live on user doc + profile)
    if u.get("role") == "student":
        out["interviews_attended"] = int(u.get("interviews_attended") or 0)
        out["student_rating"] = float(u.get("student_rating") or 0)
        out["student_ratings_count"] = int(u.get("student_ratings_count") or 0)
        # Per-action credit cost driven by profile category (Fresher/Experienced).
        out["action_cost"] = get_action_cost(u)
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


async def send_html_email(
    to_email: str,
    subject: str,
    html: str,
    mock_purpose: str = "",
    fallback_text: str = "",
    attachments: Optional[list[dict]] = None,
) -> bool:
    """Send HTML email. Provider order: Resend (preferred) → SendGrid (legacy fallback) → mock log.

    `attachments`: list of dicts {filename, content_bytes (bytes), mime_type}.
    Returns True if the email was successfully accepted by a provider.
    """
    # Full mock mode — no provider configured at all
    if MOCK_OTP_MODE:
        logger.info("[MOCK-EMAIL] to=%s purpose=%s subject=%s", to_email, mock_purpose, subject)
        return False  # caller may include OTP in response

    import base64 as _b64

    # --- Provider 1: Resend (preferred) ---
    if RESEND_API_KEY:
        try:
            import resend  # type: ignore
            import asyncio as _asyncio
            import time as _time

            resend.api_key = RESEND_API_KEY
            params: dict = {
                "from": RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html or fallback_text,
            }
            if attachments:
                params["attachments"] = [
                    {
                        "filename": a.get("filename", "attachment"),
                        "content": _b64.b64encode(a["content_bytes"]).decode("ascii"),
                        "content_type": a.get("mime_type", "application/octet-stream"),
                    }
                    for a in attachments
                ]
            # Global throttle so concurrent callers respect Resend free tier (2 req/sec).
            # We hold the lock for the duration of the request AND for any wait time
            # required so the next coroutine waits its full share too.
            global _resend_last_sent_monotonic
            async with _resend_lock:
                now = _time.monotonic()
                wait = (_resend_last_sent_monotonic + RESEND_MIN_GAP_SECS) - now
                if wait > 0:
                    await _asyncio.sleep(wait)
                # resend.Emails.send is sync; run in a thread so we don't block the event loop
                resp = await _asyncio.to_thread(resend.Emails.send, params)
                _resend_last_sent_monotonic = _time.monotonic()
            email_id = (resp or {}).get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
            logger.info("Resend OK to=%s subject=%s id=%s", to_email, subject, email_id)
            return True
        except Exception as e:
            logger.warning("Resend send failed (%s): %s — falling back to SendGrid if configured", subject, e)

    # --- Provider 2: SendGrid (legacy fallback) ---
    if SENDGRID_API_KEY:
        try:
            from sendgrid import SendGridAPIClient  # type: ignore
            from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition  # type: ignore

            msg = Mail(
                from_email=SENDGRID_FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=html or fallback_text,
            )
            if attachments:
                for a in attachments:
                    encoded = _b64.b64encode(a["content_bytes"]).decode("ascii")
                    msg.attachment = Attachment(
                        FileContent(encoded),
                        FileName(a.get("filename", "attachment")),
                        FileType(a.get("mime_type", "application/octet-stream")),
                        Disposition("attachment"),
                    )
            resp = SendGridAPIClient(SENDGRID_API_KEY).send(msg)
            return 200 <= resp.status_code < 300
        except Exception as e:
            logger.warning("SendGrid send failed (%s): %s", subject, e)
            return False

    return False


def build_interview_ics(summary: str, description: str, location: str, start_iso: str, end_iso: str, uid: str) -> bytes:
    """Build a minimal RFC-5545 .ics calendar invite for a single VEVENT."""
    def _fmt(iso: str) -> str:
        try:
            d = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
            return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = _fmt(start_iso)
    dtend = _fmt(end_iso)
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    desc_safe = (description or "").replace("\\n", "\\\\n").replace(",", "\\,").replace(";", "\\;")
    summary_safe = (summary or "").replace(",", "\\,").replace(";", "\\;")
    location_safe = (location or "").replace(",", "\\,").replace(";", "\\;")
    ics = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ReferME//Mock Interview//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}@referme.app",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary_safe}",
        f"DESCRIPTION:{desc_safe}",
        f"LOCATION:{location_safe}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    return ics.encode("utf-8")


def _build_candidate_summary(u: dict) -> str:
    p = u.get("profile", {}) or {}
    bits = []
    if p.get("preferred_role"):
        bits.append(p["preferred_role"].title())
    yoe = p.get("years_of_experience")
    if isinstance(yoe, int):
        bits.append(f"{yoe} yrs exp")
    if p.get("current_location"):
        bits.append(p["current_location"])
    skills = (p.get("skills") or [])[:5]
    if skills:
        bits.append("Skills: " + ", ".join(skills))
    return " • ".join(bits) or "—"


def _booking_email_html(role: str, slot: dict, candidate: dict, pro: dict, meeting: str, candidate_summary: str) -> str:
    when = slot.get("start_at", "")
    end_when = slot.get("end_at", "")
    pro_name = slot.get("pro_name") or (pro or {}).get("name") or "(pro)"
    student_name = candidate.get("name") or candidate.get("email", "").split("@")[0]
    skills = ", ".join(slot.get("skill_set", []) or []) or "—"
    accent = "#FF5A5F" if role == "student" else "#7C3AED"
    title = "Interview confirmed 🎉" if role == "student" else "New Mock Interview booking"
    intro = (
        f"You're booked with <b>{pro_name}</b>." if role == "student"
        else f"<b>{student_name}</b> just booked your mock interview slot."
    )
    extra_block = "" if role == "student" else f"""
      <p style="margin:8px 0 4px"><b>Candidate Profile Summary</b></p>
      <p style="margin:0;color:#374151">{candidate_summary}</p>
    """
    return f"""
      <div style="font-family:-apple-system,Arial; max-width:560px; margin:0 auto; padding:24px; background:#FDFBF7; color:#1A1A1A;">
        <h2 style="color:{accent}; margin:0 0 12px">{title}</h2>
        <p>{intro}</p>
        <ul style="line-height:1.6">
          <li><b>Candidate:</b> {student_name}</li>
          <li><b>Working Professional:</b> {pro_name}</li>
          <li><b>Skill Set:</b> {skills}</li>
          <li><b>Interview Date / Time:</b> {when} – {end_when} <span style="color:#6B7280">(IST)</span></li>
          <li><b>Meeting Link:</b> <a href="{meeting}">{meeting}</a></li>
        </ul>
        {extra_block}
        <p style="color:#6B7280;font-size:13px;margin-top:18px">An .ics calendar invitation is attached — open it on your device to add this meeting to your calendar.</p>
      </div>
    """


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
    ref: Optional[str] = None  # Referrer's referral code (e.g., USER12345)


class VerifyOtpBody(BaseModel):
    email: EmailStr
    otp: str
    purpose: Literal["verify_email", "reset_password"] = "verify_email"


class PhoneOtpSendBody(BaseModel):
    phone: str


class PhoneOtpVerifyBody(BaseModel):
    phone: str
    otp: str


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


OPEN_POSITIONS_OPTIONS = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "20+", "50+", "100+", "500+", "1000+",
]


class JobPostBody(BaseModel):
    title: str
    company: Optional[str] = None
    description: str
    location: str  # canonical city string OR "__OTHER__"
    location_other: Optional[str] = None  # used only when location == "__OTHER__"
    salary_range: Optional[str] = ""  # legacy/free-text fallback
    salary_range_label: Optional[Literal["Not disclosed","0-3", "3-5", "5-10", "10-20", "20-50", "50+"]] = "Not disclosed"
    industry_type: Optional[str] = None  # one of INDUSTRY_OPTIONS values incl. "__OTHER__"
    industry_other: Optional[str] = None  # required when industry_type == "__OTHER__"
    skills_required: Optional[list[str]] = None
    category: Literal["fresher", "experienced", "intern"] = "fresher"
    experience_required: Optional[int] = 0  # legacy; kept for back-compat
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    open_positions: Optional[int] = None  # numeric (legacy)
    open_positions_label: Optional[str] = "1"  # one of OPEN_POSITIONS_OPTIONS
    bulk_openings: Optional[int] = None  # backward compat alias
    # Proof of opening (mandatory for professionals: at least one of screenshot OR link)
    proof_screenshot_b64: Optional[str] = None  # data URI or raw base64 (JPG/PNG/PDF)
    proof_screenshot_mime: Optional[str] = None  # image/jpeg | image/png | application/pdf
    proof_link: Optional[str] = None


class JobPatchBody(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    location_other: Optional[str] = None
    salary_range: Optional[str] = None
    salary_range_label: Optional[Literal["Not disclosed", "0-3", "3-5", "5-10", "10-20", "20-50", "50+"]] = "Not disclosed"
    industry_type: Optional[str] = None
    industry_other: Optional[str] = None
    skills_required: Optional[list[str]] = None
    category: Optional[Literal["fresher", "experienced", "intern"]] = None
    experience_required: Optional[int] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    open_positions: Optional[int] = None
    open_positions_label: Optional[str] = None  # one of OPEN_POSITIONS_OPTIONS


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
    feedback: str = Field(min_length=20)
    # Interview proof screenshot (data URL or raw base64). Required.
    proof_screenshot: str = Field(min_length=20)


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


# Auth endpoints moved to routers/auth.py (Phase C).
# Helpers (normalize_indian_mobile, is_valid_indian_mobile, require_phone_verified)
# stay in server.py because they are shared by wallet.py, interviews.py, and this file's PUT /profile.


def normalize_indian_mobile(raw: str) -> tuple[str, str | None]:
    """
    Validate and normalize an Indian mobile number to E.164 (+91XXXXXXXXXX).

    Returns (normalized_or_empty, error_message_or_None).
    Accepts: 8989849312 / 918989849312 / +918989849312 / +91-8989849312 / +91 8989849312
    Rejects anything not matching the 10-digit Indian format starting with 6/7/8/9.
    """
    if not raw:
        return "", "Please enter a valid 10-digit Indian mobile number."
    s = str(raw).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    # Strip leading 91 if length is 12; strip leading 0 if length is 11.
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    # If user typed +91 with extra country prefix
    if len(digits) > 10 and digits.startswith("91") and len(digits) - 2 == 10:
        digits = digits[2:]

    # Country code check: only +91 allowed when present
    if s.startswith("+") and not (s.lstrip("+").replace("-", "").replace(" ", "").startswith("91")):
        return "", "Please enter a valid Indian mobile number with country code +91."

    if len(digits) != 10:
        return "", "Please enter a valid 10-digit Indian mobile number."

    if digits[0] not in "6789":
        return "", "Indian mobile numbers must start with 6, 7, 8, or 9."

    return f"+91{digits}", None


def is_valid_indian_mobile(raw: str) -> bool:
    _, err = normalize_indian_mobile(raw)
    return err is None


# ------------------- Phone-verified gate (Pro safety) -------------------
PRO_PHONE_GATE_MSG = "Please add and verify your mobile number to continue. Go to Profile → Verify Mobile Number."


async def require_phone_verified(u: dict) -> None:
    """Reject the request if the Working Professional has not verified their mobile number."""
    if u.get("role") != "professional":
        return
    fresh = await db.users.find_one({"id": u["id"]}, {"_id": 0, "profile.phone_verified": 1, "profile.phone": 1})
    prof = (fresh or {}).get("profile") or {}
    if not prof.get("phone_verified") or not prof.get("phone"):
        raise HTTPException(status_code=403, detail=PRO_PHONE_GATE_MSG)


# Auth + Phone-OTP + Google + Gmail-OTP + /auth/me endpoints moved to routers/auth.py (Phase C).


STUDENT_PROFILE_FIELDS_END = True  # marker



STUDENT_PROFILE_FIELDS = [
    "phone", "phone_verified", "phone_verified_at",
    "gender", "education", "education_details", "passed_out_year", "current_location",
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
    "gender", "education", "education_details",
]
EMPLOYER_PROFILE_FIELDS = ["company_name", "company_website", "company_size", "company_logo_base64", "bio"]


def compute_pro_profile_completion(user: dict) -> int:
    """Working professional profile completion percentage based on 9 mandatory factors."""
    return 100 - int(round(len(pro_missing_fields(user)) / 9 * 100))


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
    # Profile Photo is OPTIONAL per spec — do not flag as missing.
    return missing


def _education_score(edu: str) -> int:
    """Education Qualification — max 30 points per spec."""
    if not edu:
        return 0
    e = str(edu).strip().upper().replace(".", "").replace(" ", "")
    # Normalise common variants
    # B.Tech / M.Tech / BPharma / MCA / MSc / MCom → 30
    top = {"BTECH", "MTECH", "BPHARMA", "BPHARM", "MCA", "MSC", "MCOM"}
    mid_25 = {"DEGREE", "BCA", "BBA", "BA", "BCOM", "BSC"}  # generic Degree variants
    mid_20 = {"BED", "OTHER", "__OTHER__"}
    low_15 = {"DIPLOMA", "INTERMEDIATE", "10+2", "12TH", "PUC", "HSC"}
    low_10 = {"HIGHSCHOOL", "SSC", "10TH", "MATRIC"}
    if e in top:
        return 30
    if e in mid_25:
        return 25
    if e in mid_20:
        return 20
    if e in low_15 or "INTERMEDIATE" in e:
        return 15
    if e in low_10 or "HIGHSCHOOL" in e or "MATRIC" in e:
        return 10
    # Try to recognise patterns like "B Tech" / "Bachelor of Technology"
    if "TECH" in e or "PHARM" in e or e.startswith("M") and ("SC" in e or "COM" in e or "TECH" in e):
        return 30
    if "BCA" in e or "BBA" in e or "DEGREE" in e or "BACHELOR" in e:
        return 25
    if "BED" in e:
        return 20
    if "DIPLOMA" in e:
        return 15
    return 20  # default → "Other"


def _passed_year_score(year: Any, is_experienced: bool) -> int:
    """Passed Out Year — max 20 points per spec."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return 0
    if y <= 0 or y > 2100:
        return 0
    now_year = datetime.utcnow().year
    diff = now_year - y
    if diff < 0:
        diff = 0
    if is_experienced:
        # Ascending: older grad year → higher score
        if diff > 10:
            return 20
        if diff >= 6:
            return 15
        if diff >= 3:
            return 10
        return 5
    # Fresher: descending (newer grad → higher)
    if diff <= 2:
        return 20
    if diff <= 5:
        return 15
    if diff <= 10:
        return 10
    return 5


def _skills_score(skills: Any) -> int:
    """Skill Set — max 30 points per spec."""
    if isinstance(skills, str):
        items = [s.strip() for s in skills.split(",") if s.strip()]
    elif isinstance(skills, list):
        items = [str(s).strip() for s in skills if str(s).strip()]
    else:
        items = []
    n = len(items)
    if n >= 10:
        return 30
    if n >= 5:
        return 25
    if n >= 3:
        return 20
    if n == 2:
        return 15
    if n == 1:
        return 10
    return 0


def _resume_upload_score(profile: dict) -> int:
    """Resume Upload — max 20 points per spec.
    20 → uploaded and 'parsed' (has at least basic structure inferred from key profile fields).
    10 → uploaded but key fields missing.
    0  → no resume.
    """
    has_resume = bool(profile.get("resume_base64") or profile.get("resume_link"))
    if not has_resume:
        return 0
    # Treat resume as 'parsed' when core fields exist alongside it
    key_fields = ["education", "passed_out_year", "current_location", "phone"]
    missing = sum(1 for f in key_fields if not profile.get(f))
    if missing == 0:
        return 20
    return 10


def compute_resume_score(user: dict) -> int:
    """Resume Score (0-100) per official ReferME formula:
       Education(30) + Passed Out Year(20) + Skills(30) + Resume Upload(20)."""
    profile = user.get("profile", {}) or {}
    is_experienced = (profile.get("preferred_role") == "experienced") or (
        int(profile.get("years_of_experience") or 0) > 0
    )
    score = (
        _education_score(profile.get("education") or "")
        + _passed_year_score(profile.get("passed_out_year"), is_experienced)
        + _skills_score(profile.get("skills"))
        + _resume_upload_score(profile)
    )
    return max(0, min(100, int(score)))


def compute_resume_score_breakdown(user: dict) -> dict:
    """Same as compute_resume_score but returns the per-section breakdown for UI display."""
    profile = user.get("profile", {}) or {}
    is_experienced = (profile.get("preferred_role") == "experienced") or (
        int(profile.get("years_of_experience") or 0) > 0
    )
    edu_s = _education_score(profile.get("education") or "")
    year_s = _passed_year_score(profile.get("passed_out_year"), is_experienced)
    skill_s = _skills_score(profile.get("skills"))
    resume_s = _resume_upload_score(profile)
    total = max(0, min(100, edu_s + year_s + skill_s + resume_s))
    # Suggestions for improvement
    skills_list = profile.get("skills") or []
    if isinstance(skills_list, str):
        skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
    suggestions = []
    if not (profile.get("resume_base64") or profile.get("resume_link")):
        suggestions.append("Upload your resume to add up to 20 points.")
    elif resume_s < 20:
        suggestions.append("Complete missing profile fields (education, passed out year, location, phone) to unlock full resume points.")
    if len(skills_list) < 10:
        if len(skills_list) == 0:
            suggestions.append("Add skills (comma-separated) to your profile.")
        else:
            suggestions.append(f"Add more skills — you have {len(skills_list)}; aim for 10+ to earn 30 points.")
    if edu_s < 30:
        suggestions.append("Update your highest education qualification.")
    if year_s < 20:
        suggestions.append("Confirm your passed-out year matches your career stage.")
    return {
        "total": total,
        "max": 100,
        "education_score": edu_s,
        "education_max": 30,
        "passed_out_year_score": year_s,
        "passed_out_year_max": 20,
        "skills_score": skill_s,
        "skills_max": 30,
        "resume_upload_score": resume_s,
        "resume_upload_max": 20,
        "suggestions": suggestions,
    }



# ------------------- Talent Potential Score (TPS) -------------------
# Master skill list used for dropdown options (combined with skills from profiles + jobs)
MASTER_SKILLS = [
    "Oracle SQL", "PLSQL", "Java", "Python", "JavaScript", "TypeScript",
    "React", "React Native", "Angular", "Vue", "Node.js",
    "AWS", "Azure", "GCP", "DevOps", "Kubernetes", "Docker",
    "Data Science", "Machine Learning", "Deep Learning", "NLP",
    "SQL", "MongoDB", "PostgreSQL", "MySQL",
    "Spring Boot", "Django", "FastAPI", "Flask",
    "Android", "iOS", "Swift", "Kotlin",
    "HTML", "CSS", "Sass", "Tailwind",
    "Go", "Rust", "C++", "C#", ".NET",
    "Power BI", "Tableau", "Excel",
]


def _interview_count_score(interviews: int) -> int:
    """Map interview count to bucket score (max 30)."""
    n = int(interviews or 0)
    if n <= 0:
        return 0
    if n <= 2:
        return 15
    if n <= 5:
        return 25
    return 30


def compute_tps(user: dict) -> float:
    """Talent Potential Score (0-100).

    Formula:
        TPS = (resume_score * 0.60)
            + (interview_pct  * 0.20)
            + (rating_pct     * 0.20)

    - resume_score: 0-100 (existing rubric).
    - interview_pct: bucket score (0/15/25/30) normalised to /30 * 100.
    - rating_pct: stored avg student rating (1-10 scale) normalised to /10 * 100.
    """
    profile = user.get("profile") or {}
    resume_score = int(profile.get("resume_score") or 0)
    interviews = int(user.get("interviews_attended") or 0)
    avg_rating = float(user.get("student_rating") or 0)  # 0..10

    interview_score = _interview_count_score(interviews)
    interview_pct = (interview_score / 30.0) * 100.0
    rating_pct = (avg_rating / 10.0) * 100.0 if avg_rating > 0 else 0.0

    tps = (resume_score * 0.60) + (interview_pct * 0.20) + (rating_pct * 0.20)
    return round(max(0.0, min(100.0, tps)), 2)


async def recalc_tps_for_user(user_id: str) -> Optional[float]:
    """Recompute and persist `profile.tps` for a student user. No-op for other roles."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u or u.get("role") != "student":
        return None
    tps = compute_tps(u)
    prof = u.get("profile") or {}
    prof["tps"] = tps
    await db.users.update_one({"id": user_id}, {"$set": {"profile": prof}})
    return tps


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
    prev_phone = (profile.get("phone") or "").strip()
    for k in role_fields:
        if k in payload:
            profile[k] = payload[k]  # allow None to clear
    # SECURITY: clients cannot self-set phone_verified via PUT /profile —
    # only the /profile/phone/verify-otp flow may set it. Reset it if phone changed.
    new_phone_raw = (profile.get("phone") or "").strip()
    if new_phone_raw:
        # Normalize + validate
        normalized, perr = normalize_indian_mobile(new_phone_raw)
        if perr:
            raise HTTPException(status_code=400, detail=perr)
        profile["phone"] = normalized
    new_phone = profile.get("phone") or ""
    if "phone" in payload and new_phone != prev_phone:
        profile["phone_verified"] = False
        profile["phone_verified_at"] = None
    elif "phone_verified" in payload:
        # ignore client-supplied value; preserve prior or default to False
        profile["phone_verified"] = bool(profile.get("phone_verified", False))

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
    # Refresh TPS for students whenever profile (and resume_score) changes.
    if role == "student":
        await recalc_tps_for_user(u["id"])
    u2 = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    return {"user": user_public(u2), "profile": u2.get("profile", {})}


# ------------------- Wallet & Subscription -------------------
# Wallet endpoints moved to routers/wallet.py in Phase C.
# The helpers below (_can_use_free, _credit_user) stay here because they are shared
# by other routers (interviews, jobs, applications) and by admin endpoints below.


def _can_use_free(u: dict, kind: str) -> bool:
    """Returns True if the user has free uses left for free actions (booking/apply)."""
    return u.get("free_uses_left", 0) > 0


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


# Deposit endpoints moved to routers/wallet.py (Phase C).


# ------------------- Mock Interviews -------------------

# Jobs, Applications & Professionals endpoints moved to routers/jobs.py (Phase C).

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


@api.get("/admin/users/search")
async def admin_users_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None, description="Search ID/name/mobile/email/company/skill"),
    user_type: Optional[str] = Query(None),  # student | professional | employer
    location: Optional[str] = Query(None),
    profile_status: Optional[str] = Query(None),  # active | inactive | suspended
    mobile_verified: Optional[str] = Query(None),  # 'verified' | 'not_verified'
    email_verified: Optional[str] = Query(None),
    registration_range: Optional[str] = Query(None),  # today | last_7 | last_30 | custom
    registration_from: Optional[str] = Query(None),  # YYYY-MM-DD
    registration_to: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    f: dict = {}
    if user_type in ("student", "professional", "employer"):
        f["role"] = user_type
    if location:
        f["profile.current_location"] = {"$regex": re.escape(location), "$options": "i"}
    if profile_status == "suspended":
        f["account_status"] = "suspended"
    elif profile_status == "active":
        f["account_status"] = {"$ne": "suspended"}
        f["profile_complete"] = True
    elif profile_status == "inactive":
        f["account_status"] = {"$ne": "suspended"}
        f["profile_complete"] = False
    if email_verified == "verified":
        f["is_email_verified"] = True
    elif email_verified == "not_verified":
        f["is_email_verified"] = {"$ne": True}
    if mobile_verified == "verified":
        f["profile.phone_verified"] = True
    elif mobile_verified == "not_verified":
        f["profile.phone_verified"] = {"$ne": True}
    # Registration date filter
    now_dt = datetime.now(timezone.utc)
    if registration_range == "today":
        start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        f["created_at"] = {"$gte": start}
    elif registration_range == "last_7":
        f["created_at"] = {"$gte": (now_dt - timedelta(days=7)).isoformat().replace("+00:00", "Z")}
    elif registration_range == "last_30":
        f["created_at"] = {"$gte": (now_dt - timedelta(days=30)).isoformat().replace("+00:00", "Z")}
    elif registration_range == "custom":
        rng: dict = {}
        if registration_from:
            rng["$gte"] = registration_from
        if registration_to:
            rng["$lte"] = registration_to + "T23:59:59Z"
        if rng:
            f["created_at"] = rng
    # Free-text search across multiple fields
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [
            {"id": regex}, {"name": regex}, {"email": regex},
            {"profile.phone": regex},
            {"profile.company": regex}, {"profile.company_name": regex},
            {"profile.skills": regex},
            {"profile.current_location": regex},
        ]
    users = await db.users.find(f, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(limit)
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
        # Refund the exact amount the student was charged for this booking
        # (persisted on the slot at booking time — falls back to legacy ACTION_COST).
        refund_amount = int(slot.get("credits_charged") or ACTION_COST)
        await _credit_user(slot["student_id"], refund_amount, "interview_cancel_refund", {"slot_id": slot_id, "amount": refund_amount})
        await push_notification(slot["student_id"], "Interview cancelled", f"{refund_amount} credits refunded.", "warning")
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
    deposits = await db.deposit_orders.find({"status": "paid"}, {"_id": 0, "amount_inr": 1, "created_at": 1}).to_list(20000)
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


# ------------------- Admin: Rich Sectional Overview (Item #2 — Phase A) -------------------
@api.get("/admin/stats/overview")
async def admin_stats_overview(_: dict = Depends(admin_only)):
    """Per-module KPI groups for the admin dashboard — calculated dynamically from live data."""
    now_dt = datetime.now(timezone.utc)
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    month_start_dt = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = month_start_dt.isoformat().replace("+00:00", "Z")

    # USERS
    users = {
        "total": await db.users.count_documents({}),
        "students": await db.users.count_documents({"role": "student"}),
        "professionals": await db.users.count_documents({"role": "professional"}),
        "employers": await db.users.count_documents({"role": "employer"}),
        "active": await db.users.count_documents({"account_status": {"$ne": "suspended"}}),
        "new_today": await db.users.count_documents({"created_at": {"$gte": today_start}}),
    }
    # JOBS
    jobs = {
        "total": await db.jobs.count_documents({}),
        "active": await db.jobs.count_documents({"status": "open"}),
        "closed": await db.jobs.count_documents({"status": "closed"}),
        "posted_today": await db.jobs.count_documents({"created_at": {"$gte": today_start}}),
    }
    # APPLICATIONS
    app_status_counts: dict[str, int] = {}
    for r in await db.applications.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(50):
        app_status_counts[r["_id"]] = r["n"]
    apps = {
        "total": await db.applications.count_documents({}),
        "applied": app_status_counts.get("applied", 0),
        "shortlisted": app_status_counts.get("shortlisted", 0),
        "referred": app_status_counts.get("referred", 0),
        "interview_scheduled": app_status_counts.get("interview_scheduled", 0) + app_status_counts.get("awaiting_interview", 0),
        "hired": app_status_counts.get("hired", 0),
        "rejected": app_status_counts.get("rejected", 0),
    }
    # INTERVIEWS
    interview_status_counts: dict[str, int] = {}
    for r in await db.interview_slots.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(20):
        interview_status_counts[r["_id"]] = r["n"]
    interviews = {
        "slots_total": await db.interview_slots.count_documents({}),
        "available": interview_status_counts.get("available", 0),
        "booked": interview_status_counts.get("booked", 0),
        "completed": interview_status_counts.get("completed", 0),
        "cancelled": interview_status_counts.get("cancelled", 0),
    }
    # CREDITS — sum txn amounts by reason bucket
    credit_buckets = {"purchased": 0, "used": 0, "earned": 0, "rewarded": 0}
    REWARD_REASONS = {"interview_pro_reward", "job_post_reward", "hiring_reward", "referral_hired_reward", "mock_interview_reward"}
    USED_REASONS = {"job_application", "interview_booking"}
    # Wallet deposit reasons written by different code paths — accept all of them.
    PURCHASE_REASONS = {"wallet_deposit", "wallet_deposit_confirm", "credit_purchase", "deposit", "signup_bonus", "first_deposit_bonus"}
    # Transactions are stored with the signed amount on the field name `delta` — historical
    # readers referenced `amount` (which does not exist) and always saw 0. Read both for safety.
    async for t in db.transactions.find({}, {"_id": 0, "delta": 1, "amount": 1, "reason": 1}):
        amt = int(t.get("delta", t.get("amount", 0)) or 0)
        reason = t.get("reason", "")
        if amt > 0:
            if reason in PURCHASE_REASONS:
                credit_buckets["purchased"] += amt
            else:
                credit_buckets["earned"] += amt
                if reason in REWARD_REASONS:
                    credit_buckets["rewarded"] += amt
        else:
            if reason in USED_REASONS:
                credit_buckets["used"] += -amt
    credits = credit_buckets
    # REVENUE
    today_rev = 0
    month_rev = 0
    total_rev = 0
    async for d in db.deposit_orders.find({"status": "paid"}, {"_id": 0, "amount_inr": 1, "created_at": 1}):
        amt = int(d.get("amount_inr", 0))
        total_rev += amt
        c = d.get("created_at", "")
        if c >= today_start:
            today_rev += amt
        if c >= month_start:
            month_rev += amt
    revenue = {"total_inr": total_rev, "today_inr": today_rev, "monthly_inr": month_rev}
    return {"users": users, "jobs": jobs, "applications": apps,
            "interviews": interviews, "credits": credits, "revenue": revenue}


# ------------------- Admin: Filtered Jobs (Item #3) -------------------
@api.get("/admin/jobs/search")
async def admin_jobs_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None, description="Global search across id/title/company"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    salary_range: Optional[str] = Query(None),
    posted_date: Optional[str] = Query(None, description="YYYY-MM-DD; jobs posted on this date"),
    job_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(200, le=1000),
):
    f: dict = {}
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"id": regex}, {"title": regex}, {"company": regex}]
    if company:
        f["company"] = {"$regex": re.escape(company), "$options": "i"}
    if location:
        f["location"] = {"$regex": re.escape(location), "$options": "i"}
    if category:
        f["category"] = category
    if industry:
        f["industry_type"] = {"$regex": re.escape(industry), "$options": "i"}
    if salary_range:
        f["salary_range_label"] = salary_range
    if job_status:
        f["status"] = job_status
    if posted_date:
        f["created_at"] = {"$gte": posted_date, "$lt": posted_date + "T23:59:59Z"}
    jobs = await db.jobs.find(f, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # annotate counts
    if jobs:
        ids = [j["id"] for j in jobs]
        agg = await db.applications.aggregate([
            {"$match": {"job_id": {"$in": ids}}},
            {"$group": {"_id": {"job": "$job_id", "status": "$status"}, "n": {"$sum": 1}}},
        ]).to_list(5000)
        amap: dict[str, int] = {}
        smap: dict[str, int] = {}
        for r in agg:
            jid = r["_id"]["job"]
            st = r["_id"]["status"]
            if st == "withdrawn":
                continue
            amap[jid] = amap.get(jid, 0) + r["n"]
            if st in ("shortlisted", "interview_scheduled", "awaiting_interview", "hired"):
                smap[jid] = smap.get(jid, 0) + r["n"]
        for j in jobs:
            j["applied_count"] = amap.get(j["id"], 0)
            j["shortlisted_count"] = smap.get(j["id"], 0)
    return jobs


# ------------------- Admin: Filtered Interview Slots (Item #4) -------------------
@api.get("/admin/interviews/search")
async def admin_interviews_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None),
    candidate: Optional[str] = Query(None),
    pro: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    date: Optional[str] = Query(None),  # YYYY-MM-DD start_at on that day
    slot_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(300, le=2000),
):
    f: dict = {}
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"id": regex}, {"student_name": regex}, {"pro_name": regex}, {"meeting_url": regex}]
    if candidate:
        f["student_name"] = {"$regex": re.escape(candidate), "$options": "i"}
    if pro:
        f["pro_name"] = {"$regex": re.escape(pro), "$options": "i"}
    if skill:
        f["skill_set"] = {"$regex": re.escape(skill), "$options": "i"}
    if slot_status:
        f["status"] = slot_status
    if date:
        f["start_at"] = {"$gte": date, "$lt": date + "T23:59:59Z"}
    slots = await db.interview_slots.find(f, {"_id": 0}).sort("start_at", -1).to_list(limit)
    return slots


# ------------------- Admin: Credit Transactions (Item #5) -------------------
@api.get("/admin/transactions/search")
async def admin_transactions_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),  # student | professional | employer
    type: Optional[str] = Query(None, description="purchase | application | interview_reward | job_post_reward | hiring_reward | manual"),
    date_from: Optional[str] = Query(None),  # YYYY-MM-DD inclusive
    date_to: Optional[str] = Query(None),
    limit: int = Query(500, le=5000),
):
    txn_filter: dict = {}
    # Map UI transaction type → internal `reason` set
    type_map = {
        "purchase": {"wallet_deposit", "wallet_deposit_confirm", "credit_purchase"},
        "application": {"job_application"},
        "interview_reward": {"interview_pro_reward"},
        "job_post_reward": {"job_post_reward"},
        "hiring_reward": {"hiring_reward", "referral_hired_reward"},
        "manual": {"admin_refund", "admin_adjustment"},
    }
    if type and type in type_map:
        txn_filter["reason"] = {"$in": list(type_map[type])}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59Z"
        txn_filter["created_at"] = rng
    transactions = await db.transactions.find(txn_filter, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # Hydrate user details (name / email / role)
    user_ids = list({t.get("user_id") for t in transactions if t.get("user_id")})
    users_lookup: dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}):
            users_lookup[u["id"]] = u
    out = []
    for t in transactions:
        u = users_lookup.get(t.get("user_id"), {})
        if user_type and u.get("role") != user_type:
            continue
        if q:
            target = " ".join([t.get("id", ""), u.get("name", ""), u.get("email", ""), str(t.get("reason", ""))]).lower()
            if q.lower() not in target:
                continue
        # Transactions store the signed credit amount on the `delta` field (historical readers
        # incorrectly referenced `amount` and always saw 0). Read both for safety.
        amt = int(t.get("delta", t.get("amount", 0)) or 0)
        out.append({
            "id": t.get("id"),
            "user_id": t.get("user_id"),
            "user_name": u.get("name") or (u.get("email", "").split("@")[0] if u.get("email") else "—"),
            "user_email": u.get("email"),
            "user_type": u.get("role"),
            "credits_added": amt if amt > 0 else 0,
            "credits_deducted": -amt if amt < 0 else 0,
            "amount": amt,
            "reason": t.get("reason"),
            "reference": t.get("meta", {}),
            "created_at": t.get("created_at"),
            "status": t.get("status", "completed"),
        })
    return out


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

    # One-time slot data wipe — Item 3-7 (Jun 2026 sub-slot migration).
    # Marker doc in `settings` keeps this idempotent so we never wipe twice.
    marker = await db.settings.find_one({"key": "slot_v2_wiped"})
    if not marker:
        d_slots = await db.interview_slots.delete_many({})
        # Also wipe legacy booking history for clean slate
        try:
            await db.interview_bookings.delete_many({})
        except Exception:
            pass
        await db.settings.insert_one({"key": "slot_v2_wiped", "wiped_at": now_iso(),
                                       "slots_removed": d_slots.deleted_count if d_slots else 0})
        logger.info("Wiped %s legacy interview_slots for sub-slot v2 migration.", d_slots.deleted_count if d_slots else 0)


# ------------------- Admin: Mock Interview Booking Tracking (Item 10) -------------------
@api.get("/admin/interview-bookings")
async def admin_list_interview_bookings(u: dict = Depends(require_role(["admin"]))):
    """List every Mock Interview booking with full Pro & Student details, slot info,
    meeting link, status, booking timestamp and per-recipient email delivery status."""
    bookings = await db.interview_bookings.find({}, {"_id": 0}).sort("booked_at", -1).to_list(2000)
    # Hydrate latest slot status (in case it was cancelled/completed after booking)
    slot_ids = [b["slot_id"] for b in bookings if b.get("slot_id")]
    slot_map = {}
    if slot_ids:
        slots = await db.interview_slots.find({"id": {"$in": slot_ids}}, {"_id": 0, "id": 1, "status": 1}).to_list(2000)
        slot_map = {s["id"]: s.get("status") for s in slots}
    for b in bookings:
        b["current_slot_status"] = slot_map.get(b.get("slot_id"), "deleted")
    return bookings


# ============================================================
# CREDIT REDEMPTION (Working Professional → INR Payout)
# ============================================================
REDEMPTION_MIN_CREDITS = 500
REDEMPTION_INR_PER_CREDIT = 1.0  # 1 credit = ₹1


def _upi_valid(upi: str) -> bool:
    return bool(re.match(r"^[\w.\-_]{2,256}@[a-zA-Z]{2,64}$", (upi or "").strip()))


class RedemptionSubmitBody(BaseModel):
    credits: int = Field(ge=REDEMPTION_MIN_CREDITS)
    account_holder_name: str = Field(min_length=2, max_length=100)
    upi_id: str
    bank_account: Optional[str] = ""
    ifsc: Optional[str] = ""


class RedemptionPaidBody(BaseModel):
    payment_ref: str = Field(min_length=2, max_length=120)
    payment_date: Optional[str] = None  # ISO; defaults to now
    remarks: Optional[str] = ""


class RedemptionRejectBody(BaseModel):
    reason: str = Field(min_length=2, max_length=400)


def _redemption_inr(credits: int) -> float:
    return round(credits * REDEMPTION_INR_PER_CREDIT, 2)


# /redemption/submit and /redemption/my moved to routers/wallet.py (Phase C).


# ---- Admin redemption endpoints ----
@api.get("/admin/redemption-requests")
async def admin_list_redemptions(
    status_f: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = None,
    limit: int = 100,
    _: dict = Depends(admin_only),
):
    flt: dict[str, Any] = {}
    if status_f and status_f.lower() != "all":
        flt["status"] = status_f.lower()
    if q:
        rgx = re.compile(re.escape(q.strip()), re.IGNORECASE)
        flt["$or"] = [
            {"pro_name": rgx},
            {"pro_email": rgx},
            {"id": rgx},
            {"upi_id": rgx},
        ]
    items = await db.redemption_requests.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 500))
    counts = {}
    for s in ("pending", "approved", "paid", "rejected"):
        counts[s] = await db.redemption_requests.count_documents({"status": s})
    return {"items": items, "counts": counts}


@api.post("/admin/redemption-requests/{req_id}/approve")
async def admin_approve_redemption(req_id: str, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve a {r['status']} request")
    now = now_iso()
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "approved", "approved_at": now, "updated_at": now}},
    )
    await push_notification(
        r["pro_id"],
        "Redemption approved ✅",
        f"Your redemption of {r['credits_requested']} credits is approved. Payment in progress.",
        "success",
    )
    return {"ok": True, "status": "approved"}


@api.post("/admin/redemption-requests/{req_id}/mark-paid")
async def admin_mark_redemption_paid(req_id: str, body: RedemptionPaidBody, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] not in ("approved", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot mark a {r['status']} request as paid")
    now = now_iso()
    pay_date = body.payment_date or now
    # Burn the locked credits (payment was made out of platform)
    await db.users.update_one(
        {"id": r["pro_id"]},
        {"$inc": {"locked_credits": -r["credits_requested"]}},
    )
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "paid",
            "payment_ref": body.payment_ref.strip(),
            "payment_date": pay_date,
            "remarks": (body.remarks or "").strip(),
            "paid_at": now,
            "updated_at": now,
        }},
    )
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": r["pro_id"],
        "delta": 0,
        "reason": "redemption_paid",
        "meta": {
            "request_id": req_id,
            "credits_redeemed": r["credits_requested"],
            "amount_inr": r["amount_inr"],
            "payment_ref": body.payment_ref.strip(),
            "payment_date": pay_date,
        },
        "created_at": now,
    })
    await push_notification(
        r["pro_id"],
        "Redemption paid 💸",
        f"Your redemption request has been processed and ₹{r['amount_inr']:.2f} has been transferred to your provided account/UPI. Ref: {body.payment_ref.strip()}.",
        "success",
    )
    return {"ok": True, "status": "paid"}


@api.post("/admin/redemption-requests/{req_id}/reject")
async def admin_reject_redemption(req_id: str, body: RedemptionRejectBody, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] in ("paid", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot reject a {r['status']} request")
    now = now_iso()
    # Restore locked credits back to available
    await db.users.update_one(
        {"id": r["pro_id"]},
        {"$inc": {"locked_credits": -r["credits_requested"], "credits": r["credits_requested"]}},
    )
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "rejected",
            "rejection_reason": body.reason.strip(),
            "rejected_at": now,
            "updated_at": now,
        }},
    )
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": r["pro_id"],
        "delta": r["credits_requested"],
        "reason": "redemption_refunded",
        "meta": {"request_id": req_id, "rejection_reason": body.reason.strip()},
        "created_at": now,
    })
    await push_notification(
        r["pro_id"],
        "Redemption rejected ⚠️",
        f"Your redemption request was rejected: {body.reason.strip()}. {r['credits_requested']} credits returned to your balance.",
        "warning",
    )
    return {"ok": True, "status": "rejected"}


# Register router
# ============================================================
# ADMIN PHASE B: EDIT + AUDIT LOGS (Users / Jobs / Bookings / Credits)
# ============================================================
AUDIT_PURGE_DAYS = 90
AUDIT_PURGE_ENTITIES = {"job", "interview_booking", "interview_slot"}


async def _ensure_audit_ttl_index():
    """Create TTL index on `purge_at` so docs with that field auto-expire (used for jobs/interview audit only)."""
    try:
        await db.audit_logs.create_index("purge_at", expireAfterSeconds=0)
        await db.audit_logs.create_index([("created_at", -1)])
        await db.audit_logs.create_index([("entity_type", 1), ("entity_id", 1)])
        logger.info("audit_logs TTL + indexes ensured")
    except Exception as ex:
        logger.warning("Could not ensure audit indexes: %s", ex)


@app.on_event("startup")
async def _audit_startup():
    await _ensure_audit_ttl_index()


def _diff_doc(before: dict, after: dict) -> dict:
    """Return only changed keys with {key: {before, after}}."""
    out: dict[str, Any] = {}
    keys = set((before or {}).keys()) | set((after or {}).keys())
    for k in keys:
        b = (before or {}).get(k)
        a = (after or {}).get(k)
        if b != a:
            out[k] = {"before": b, "after": a}
    return out


async def write_audit(
    actor: dict,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
    extra: dict | None = None,
) -> None:
    """Write an audit-log entry. Jobs / interview entries auto-purge after 90 days via TTL."""
    now = now_iso()
    doc: dict[str, Any] = {
        "id": new_id(),
        "actor_id": actor.get("id", ""),
        "actor_email": actor.get("email", ""),
        "actor_name": actor.get("name", "") or actor.get("email", ""),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": before or {},
        "after": after or {},
        "diff": _diff_doc(before or {}, after or {}) if (before or after) else {},
        "reason": (reason or "").strip(),
        "extra": extra or {},
        "created_at": now,
    }
    if entity_type in AUDIT_PURGE_ENTITIES:
        doc["purge_at"] = datetime.utcnow() + timedelta(days=AUDIT_PURGE_DAYS)
    try:
        await db.audit_logs.insert_one(doc)
    except Exception as ex:
        logger.warning("audit write failed (%s): %s", action, ex)


# ---- Edit User ----
class AdminEditUserBody(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None  # student | professional | employer | admin
    account_status: Optional[str] = None  # active | suspended
    reason: Optional[str] = ""


@api.patch("/admin/users/{user_id}")
async def admin_edit_user(user_id: str, body: AdminEditUserBody, admin: dict = Depends(admin_only)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    allowed_roles = {"student", "professional", "employer", "admin"}
    allowed_status = {"active", "suspended"}

    update: dict[str, Any] = {}
    if body.name is not None:
        update["name"] = body.name.strip()
    if body.role is not None:
        if body.role not in allowed_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {sorted(allowed_roles)}")
        update["role"] = body.role
    if body.account_status is not None:
        if body.account_status not in allowed_status:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(allowed_status)}")
        update["account_status"] = body.account_status

    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided.")

    before_snap = {k: user.get(k) for k in update.keys()}
    await db.users.update_one({"id": user_id}, {"$set": update})
    after_snap = update
    await write_audit(
        admin, "user.edit", "user", user_id,
        before=before_snap, after=after_snap, reason=body.reason or "",
        extra={"target_email": user.get("email", "")},
    )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"ok": True, "user": updated}


# ---- Adjust Credits ----
class AdminCreditAdjustBody(BaseModel):
    delta: int = Field(..., description="Positive to add, negative to remove")
    reason: str = Field(min_length=2, max_length=400)


@api.post("/admin/users/{user_id}/credits/adjust")
async def admin_adjust_credits(user_id: str, body: AdminCreditAdjustBody, admin: dict = Depends(admin_only)):
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="Delta must be non-zero.")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    before_credits = user.get("credits", 0)

    # If deducting, ensure not going below zero
    if body.delta < 0 and before_credits + body.delta < 0:
        raise HTTPException(status_code=400, detail=f"Cannot deduct {-body.delta}. User has only {before_credits} credits.")

    now = now_iso()
    await db.users.update_one({"id": user_id}, {"$inc": {"credits": body.delta}})
    # Ledger entry
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "delta": body.delta,
        "reason": "admin_adjustment",
        "meta": {
            "label": f"Admin Adjustment ({'+' if body.delta > 0 else ''}{body.delta})",
            "admin_id": admin.get("id", ""),
            "admin_email": admin.get("email", ""),
            "note": body.reason,
        },
        "created_at": now,
    })
    after_credits = before_credits + body.delta
    await write_audit(
        admin, "user.credits.adjust", "credit_adjustment", user_id,
        before={"credits": before_credits},
        after={"credits": after_credits},
        reason=body.reason,
        extra={"target_email": user.get("email", ""), "delta": body.delta},
    )
    await push_notification(
        user_id,
        f"Credits {'added' if body.delta > 0 else 'adjusted'}",
        f"{abs(body.delta)} credits {'added to' if body.delta > 0 else 'deducted from'} your wallet by admin. New balance: {after_credits}.",
        "info",
    )
    return {"ok": True, "credits": after_credits, "delta": body.delta}


# ---- Edit Job ----
# NOTE: The full admin edit-job endpoint has moved to routers/admin_jobs.py which
# supports every AdminJobBody field (walk-in, contacts, skills, logo, status draft|open|closed).
# The legacy stub that lived here shadowed the router handler and rejected valid statuses,
# so it was removed. If you need the tiny "title/description/status active|closed" shape
# retained by some old admin UIs, use PATCH /api/admin/jobs/{id} with the newer schema —
# the router accepts partial payloads via AdminJobPatchBody.

# ---- Cancel Booking (Admin) — auto-refund credits to student (99 or 199, per stored credits_charged) ----
class AdminCancelBookingBody(BaseModel):
    reason: str = Field(min_length=2, max_length=400)
    refund: Optional[bool] = True


@api.post("/admin/interviews/bookings/{booking_id}/cancel")
async def admin_cancel_booking(booking_id: str, body: AdminCancelBookingBody, admin: dict = Depends(admin_only)):
    bk = await db.interview_bookings.find_one({"id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    if bk.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Booking already cancelled.")
    now = now_iso()

    # Release the slot back to 'available' so other students can book it
    if bk.get("slot_id"):
        await db.interview_slots.update_one(
            {"id": bk["slot_id"]},
            {"$set": {"status": "available"}, "$unset": {"student_id": "", "student_name": "", "student_email": "", "booked_at": ""}},
        )

    # Mark booking cancelled
    await db.interview_bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "cancelled", "cancelled_at": now, "cancel_reason": body.reason, "cancelled_by": admin.get("email", "")}},
    )

    # Refund credits to student
    refund_amount = 0
    if body.refund and bk.get("student_id"):
        refund_amount = int(bk.get("credits_charged") or ACTION_COST)
        await db.users.update_one({"id": bk["student_id"]}, {"$inc": {"credits": refund_amount}})
        await db.transactions.insert_one({
            "id": new_id(),
            "user_id": bk["student_id"],
            "delta": refund_amount,
            "reason": "interview_admin_refund",
            "meta": {
                "label": "Mock Interview Refund (Admin Cancelled)",
                "booking_id": booking_id,
                "admin_id": admin.get("id", ""),
                "admin_email": admin.get("email", ""),
                "note": body.reason,
            },
            "created_at": now,
        })
        await push_notification(
            bk["student_id"],
            "Mock interview cancelled",
            f"Your booking on {bk.get('start_at','')} has been cancelled by admin. {refund_amount} credits have been refunded. Reason: {body.reason}",
            "warning",
        )
    # Notify pro
    if bk.get("pro_id"):
        await push_notification(
            bk["pro_id"],
            "Mock interview cancelled by admin",
            f"The booking with {bk.get('student_name','student')} on {bk.get('start_at','')} has been cancelled. Reason: {body.reason}",
            "info",
        )

    await write_audit(
        admin, "interview_booking.cancel", "interview_booking", booking_id,
        before={"status": bk.get("status", ""), "student_id": bk.get("student_id", "")},
        after={"status": "cancelled", "refund": refund_amount},
        reason=body.reason,
        extra={
            "student_email": bk.get("student_email", ""),
            "pro_email": bk.get("pro_email", ""),
            "slot_id": bk.get("slot_id", ""),
            "start_at": bk.get("start_at", ""),
        },
    )
    return {"ok": True, "status": "cancelled", "refund": refund_amount}


# ---- List Audit Logs ----
@api.get("/admin/audit-logs")
async def admin_list_audit_logs(
    action: Optional[str] = None,
    entity: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    _: dict = Depends(admin_only),
):
    flt: dict[str, Any] = {}
    if action:
        flt["action"] = action
    if entity:
        flt["entity_type"] = entity
    if q:
        rgx = re.compile(re.escape(q.strip()), re.IGNORECASE)
        flt["$or"] = [
            {"actor_email": rgx},
            {"actor_name": rgx},
            {"entity_id": rgx},
            {"reason": rgx},
            {"extra.target_email": rgx},
            {"extra.job_title": rgx},
        ]
    items = await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    return {
        "items": items,
        "retention_days_for_jobs_and_interviews": AUDIT_PURGE_DAYS,
    }


@api.post("/admin/interviews/slots/{slot_id}/cancel-booking")
async def admin_cancel_slot_booking(slot_id: str, body: AdminCancelBookingBody, admin: dict = Depends(admin_only)):
    """Convenience wrapper: find the active booking on this slot and cancel it."""
    bk = await db.interview_bookings.find_one({"slot_id": slot_id, "status": {"$ne": "cancelled"}}, {"_id": 0})
    if not bk:
        raise HTTPException(status_code=404, detail="No active booking found for this slot.")
    return await admin_cancel_booking(bk["id"], body, admin)


# ============================================================
# ADMIN EXPORTS — CSV & PDF for Users / Jobs / Interviews / Credits / Redemptions
# ============================================================
import csv as _csv
import io as _io
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors as rl_colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def _stream_csv(rows: list[list[Any]], header: list[str], filename: str) -> StreamingResponse:
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else str(v) for v in r])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


def _stream_pdf(rows: list[list[Any]], header: list[str], title: str, filename: str) -> StreamingResponse:
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=24, bottomMargin=18)
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(f"<b>ReferME · {title}</b>", styles["Title"]),
        Paragraph(f"Exported on {now_iso()} · {len(rows)} record(s)", styles["Normal"]),
        Spacer(1, 8),
    ]
    data = [header] + [["" if v is None else str(v)[:80] for v in r] for r in rows]
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#FF5A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, rl_colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.whitesmoke, rl_colors.white]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


def _serve(rows: list[list[Any]], header: list[str], filename: str, title: str, fmt: str):
    fmt = (fmt or "csv").lower()
    if fmt == "pdf":
        return _stream_pdf(rows, header, title, filename)
    return _stream_csv(rows, header, filename)


@api.get("/admin/export/users")
async def admin_export_users(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(10000)
    header = ["ID", "Name", "Email", "Role", "Status", "Credits", "Locked Credits", "Email Verified", "Mobile", "Mobile Verified", "Created At"]
    rows = [
        [
            u.get("id"), u.get("name"), u.get("email"), u.get("role"),
            u.get("account_status", "active"),
            u.get("credits", 0), u.get("locked_credits", 0),
            "Yes" if u.get("is_email_verified") else "No",
            (u.get("profile") or {}).get("phone", ""),
            "Yes" if (u.get("profile") or {}).get("phone_verified") else "No",
            u.get("created_at", ""),
        ]
        for u in users
    ]
    return _serve(rows, header, f"referme_users_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Users Export", fmt)


@api.get("/admin/export/jobs")
async def admin_export_jobs(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    jobs = await db.jobs.find({}, {"_id": 0}).to_list(10000)
    header = ["ID", "Title", "Company", "Location", "Industry", "Salary Range", "Status", "Posted By Email", "Created At"]
    rows = [
        [
            j.get("id"), j.get("title"), j.get("company_name", ""),
            j.get("location"), j.get("industry_type", ""), j.get("salary_range", ""),
            j.get("status", "active"), j.get("poster_email", ""),
            j.get("created_at", ""),
        ]
        for j in jobs
    ]
    return _serve(rows, header, f"referme_jobs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Jobs Export", fmt)


@api.get("/admin/export/interviews")
async def admin_export_interviews(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    slots = await db.interview_slots.find({}, {"_id": 0}).to_list(10000)
    header = ["Slot ID", "Pro Name", "Pro Email", "Student Name", "Student Email", "Skills", "Category", "Start At", "End At", "Status", "Meeting URL"]
    rows = [
        [
            s.get("id"), s.get("pro_name"), s.get("pro_email", ""),
            s.get("student_name", ""), s.get("student_email", ""),
            ", ".join(s.get("skill_set", []) or []),
            s.get("category", ""), s.get("start_at", ""), s.get("end_at", ""),
            s.get("status", ""), s.get("meeting_url", ""),
        ]
        for s in slots
    ]
    return _serve(rows, header, f"referme_interviews_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Interview Slots Export", fmt)


@api.get("/admin/export/transactions")
async def admin_export_transactions(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    txs = await db.transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(20000)
    # Resolve user emails for richer output
    user_ids = list({t.get("user_id") for t in txs if t.get("user_id")})
    user_map: dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}):
            user_map[u["id"]] = u
    header = ["Tx ID", "User Email", "User Role", "Delta", "Reason", "Label", "Created At"]
    rows = [
        [
            t.get("id"),
            (user_map.get(t.get("user_id", "")) or {}).get("email", ""),
            (user_map.get(t.get("user_id", "")) or {}).get("role", ""),
            t.get("delta", 0),
            t.get("reason", ""),
            (t.get("meta") or {}).get("label", ""),
            t.get("created_at", ""),
        ]
        for t in txs
    ]
    return _serve(rows, header, f"referme_credits_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Credit Transactions Export", fmt)


@api.get("/admin/export/redemptions")
async def admin_export_redemptions(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    items = await db.redemption_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    header = ["Request ID", "Pro Name", "Pro Email", "Credits Requested", "Amount INR", "UPI ID", "Bank Account", "IFSC", "Status", "Payment Ref", "Payment Date", "Rejection Reason", "Created At"]
    rows = [
        [
            r.get("id"), r.get("pro_name"), r.get("pro_email"),
            r.get("credits_requested", 0), f"{r.get('amount_inr', 0):.2f}",
            r.get("upi_id", ""), r.get("bank_account", ""), r.get("ifsc", ""),
            r.get("status", ""), r.get("payment_ref", ""), r.get("payment_date", ""),
            r.get("rejection_reason", ""), r.get("created_at", ""),
        ]
        for r in items
    ]
    return _serve(rows, header, f"referme_redemptions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Redemption Requests Export", fmt)


# ---- Admin Job Verification (proof of opening) ----
class AdminVerifyJobBody(BaseModel):
    decision: Literal["verified", "rejected"]
    note: Optional[str] = ""


@api.post("/admin/jobs/{job_id}/verify")
async def admin_verify_job(job_id: str, body: AdminVerifyJobBody, admin: dict = Depends(admin_only)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if body.decision == "rejected" and not (body.note or "").strip():
        raise HTTPException(status_code=400, detail="Rejection reason is required.")
    now = now_iso()
    before = {"verification_status": job.get("verification_status", "pending")}
    after = {
        "verification_status": body.decision,
        "verified_by": admin.get("email", ""),
        "verified_at": now,
        "verification_note": (body.note or "").strip(),
        "updated_at": now,
    }
    await db.jobs.update_one({"id": job_id}, {"$set": after})
    await write_audit(
        admin, "job.verify", "job", job_id,
        before=before, after={"verification_status": body.decision},
        reason=body.note or "",
        extra={"job_title": job.get("title", "")},
    )
    # Notify the poster
    if job.get("employer_id"):
        if body.decision == "verified":
            await push_notification(
                job["employer_id"],
                "Job verified ✅",
                f"Your job posting '{job.get('title','')}' has been verified and is now public.",
                "success",
            )
        else:
            await push_notification(
                job["employer_id"],
                "Job verification rejected",
                f"Your job posting '{job.get('title','')}' was rejected. Reason: {body.note or 'not specified'}",
                "warning",
            )
    return {"ok": True, "verification_status": body.decision}



# /jobs/{job_id}/resubmit moved to routers/jobs.py (Phase C).

@api.get("/student/resume-score")
async def my_resume_score(u: dict = Depends(require_role(["student"]))):
    """Return the live Resume Score breakdown so the Profile screen can render the gauge + suggestions."""
    return compute_resume_score_breakdown(u)



# ------------------- Modular routers (Phase A refactor) -------------------
# Imported at the bottom so all helper names (db, current_user, REFERRAL_REWARD,
# compute_tps, compute_wps, MASTER_SKILLS, require_role, make_referral_code,
# referral_link_for) are already defined in this module's namespace.
from routers import referrals as _referrals_router  # noqa: E402
from routers import leaderboard as _leaderboard_router  # noqa: E402
api.include_router(_referrals_router.router)
api.include_router(_leaderboard_router.router)
from routers import interviews as _interviews_router  # noqa: E402
api.include_router(_interviews_router.router)
from routers import admin_jobs as _admin_jobs_router  # noqa: E402
api.include_router(_admin_jobs_router.router)
# Phase C: wallet endpoints (/wallet, /subscription/plans, /wallet/deposit/*, /redemption/*)
from routers import wallet as _wallet_router  # noqa: E402
api.include_router(_wallet_router.router)
# Phase C part 2: auth endpoints
from routers import auth as _auth_router  # noqa: E402
api.include_router(_auth_router.router)
# Phase C part 3: jobs, applications & professionals endpoints
from routers import jobs as _jobs_router  # noqa: E402
api.include_router(_jobs_router.router)
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
