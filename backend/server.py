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
        # Profile completion (Iteration 58 — gates job applications).
        out["profile_completion"] = student_profile_completion(u)
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


class SupportTicketBody(BaseModel):
    subject: str
    description: str
    # Optional data-URI attachment (e.g. "data:image/png;base64,....") — max 5MB after decoding.
    attachment_base64: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_mime: Optional[str] = None


# Support inbox destination — hard-coded per spec (Iteration 62).
SUPPORT_EMAIL_TO = os.environ.get("SUPPORT_EMAIL_TO", "support@refermejobs.com")


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


def student_missing_fields(user: dict) -> list[str]:
    """Return the list of mandatory Job-Seeker profile fields the user hasn't filled.

    Powers the 'Profile Incomplete' popup on the Apply flow (Iteration 58) and the
    'Complete the following to apply for jobs' panel on the Job Seeker profile screen.
    The 11 mandatory fields are:
        1. Full Name             (user.name)
        2. Profile Category      (profile.preferred_role)
        3. Mobile Number         (profile.phone + profile.phone_verified)
        4. Email Address         (user.is_email_verified)
        5. Gender                (profile.gender)
        6. Date of Birth         (profile.dob)
        7. Education             (profile.education)
        8. Passed Out Year       (profile.passed_out_year)
        9. Skills                (profile.skills, non-empty list)
       10. Current Location      (profile.current_location)
       11. Resume Upload         (profile.resume_base64 OR profile.resume_link)
    """
    p = user.get("profile") or {}
    missing: list[str] = []
    if not (user.get("name") or "").strip():
        missing.append("Full Name")
    role = (p.get("preferred_role") or "").strip().lower()
    if role not in ("fresher", "experienced"):
        missing.append("Profile Category")
    phone = (p.get("phone") or "").strip()
    if not phone or not p.get("phone_verified"):
        missing.append("Verify Mobile Number")
    if not user.get("is_email_verified") and user.get("role") == "student":
        missing.append("Verify Email Address")
    if not (p.get("gender") or "").strip():
        missing.append("Gender")
    if not (p.get("dob") or "").strip():
        missing.append("Date of Birth")
    if not (p.get("education") or "").strip():
        missing.append("Education Qualification")
    elif p.get("education") == "__OTHER__" and not (p.get("education_details") or "").strip():
        missing.append("Education Qualification")
    if not p.get("passed_out_year"):
        missing.append("Passed Out Year")
    skills = p.get("skills") or []
    if not isinstance(skills, list) or len([s for s in skills if str(s).strip()]) == 0:
        missing.append("Add Skills")
    if not (p.get("current_location") or "").strip():
        missing.append("Current Location")
    if not (p.get("resume_base64") or p.get("resume_link")):
        missing.append("Upload Resume")
    return missing


def student_profile_completion(user: dict) -> int:
    """Return the Job-Seeker profile completion percentage (0..100) based on the 11 mandatory fields."""
    total = 11
    missing = len(student_missing_fields(user))
    return max(0, min(100, int(round((total - missing) / total * 100))))


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

# /admin/status-changes moved to routers/admin.py (Phase D).
# /admin/status-changes/action moved to routers/admin.py (Phase D).
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


# /admin/payouts/action moved to routers/admin.py (Phase D).
# ------------------- Admin -------------------
# /admin/users moved to routers/admin.py (Phase D).
# /admin/users/search moved to routers/admin.py (Phase D).
# /admin/users/{user_id}/suspend moved to routers/admin.py (Phase D).
# /admin/users/{user_id}/activate moved to routers/admin.py (Phase D).
# /admin/users/{user_id} moved to routers/admin.py (Phase D).
# /admin/jobs moved to routers/admin.py (Phase D).
# /admin/jobs/{job_id} moved to routers/admin.py (Phase D).
# /admin/interviews moved to routers/admin.py (Phase D).
# /admin/interviews/{slot_id} moved to routers/admin.py (Phase D).
# /admin/wallet/refund moved to routers/admin.py (Phase D).
# /admin/stats moved to routers/admin.py (Phase D).
# ------------------- Admin: Rich Sectional Overview (Item #2 — Phase A) -------------------
# /admin/stats/overview moved to routers/admin.py (Phase D).
# ------------------- Admin: Filtered Jobs (Item #3) -------------------
# /admin/jobs/search moved to routers/admin.py (Phase D).
# ------------------- Admin: Filtered Interview Slots (Item #4) -------------------
# /admin/interviews/search moved to routers/admin.py (Phase D).
# ------------------- Admin: Credit Transactions (Item #5) -------------------
# /admin/transactions/search moved to routers/admin.py (Phase D).
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


# ------------------- Support (Iteration 62 — "Raise an Issue") -------------------
@api.post("/support/tickets")
async def create_support_ticket(body: SupportTicketBody, u: dict = Depends(current_user)):
    """Create a support ticket and email it to SUPPORT_EMAIL_TO (support@refermejobs.com).

    Spec: `Raise an Issue Support Enhancement` — Subject + Description are mandatory,
    Attachment is optional. Applies to all roles (Job Seekers, Working Professionals, Admins).
    """
    subject = (body.subject or "").strip()
    description = (body.description or "").strip()
    if len(subject) < 3:
        raise HTTPException(status_code=400, detail="Subject is mandatory (min 3 characters).")
    if len(description) < 5:
        raise HTTPException(status_code=400, detail="Issue Description is mandatory (min 5 characters).")

    # Decode optional attachment (data URI) — cap at 5 MB decoded to keep the mail small.
    attachments: list[dict] = []
    if body.attachment_base64:
        import base64 as _b64
        raw = body.attachment_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            content = _b64.b64decode(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Attachment is not a valid base64 payload.")
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Attachment exceeds 5 MB limit.")
        attachments.append({
            "filename": body.attachment_filename or "attachment.bin",
            "content_bytes": content,
            "mime_type": body.attachment_mime or "application/octet-stream",
        })

    ticket_id = new_id()
    doc = {
        "id": ticket_id,
        "user_id": u["id"],
        "user_email": u.get("email"),
        "user_name": u.get("name") or "",
        "user_role": u.get("role"),
        "subject": subject,
        "description": description,
        "has_attachment": bool(attachments),
        "attachment_filename": body.attachment_filename if attachments else None,
        "status": "open",
        "created_at": now_iso(),
    }
    await db.support_tickets.insert_one(doc)

    # HTML-escape user-provided content before interpolating into the outbound email.
    import html as _html
    e_subject = _html.escape(subject)
    e_description = _html.escape(description)
    e_name = _html.escape(u.get("name") or "")
    e_email = _html.escape(u.get("email") or "")
    e_role = _html.escape(u.get("role") or "")

    # Fire-and-forget email to the support inbox (send_html_email already handles the
    # mock/provider/attachment logic + throttling).
    html = f"""
    <div style='font-family: Arial, sans-serif; color:#111; padding: 20px;'>
      <h2 style='color:#7C3AED;'>New Support Ticket · {ticket_id}</h2>
      <p><strong>From:</strong> {e_name} &lt;{e_email}&gt; ({e_role})</p>
      <p><strong>Subject:</strong> {e_subject}</p>
      <p><strong>Description:</strong></p>
      <pre style='white-space: pre-wrap; background:#f8f8fa; padding:12px; border-radius:8px;'>{e_description}</pre>
      <p style='color:#888; font-size:12px; margin-top:24px;'>Submitted at {doc['created_at']}</p>
    </div>
    """
    try:
        await send_html_email(
            SUPPORT_EMAIL_TO,
            f"[ReferME Support] {subject}",
            html,
            mock_purpose="support_ticket",
            fallback_text=f"From {u.get('email')} — {subject}\n\n{description}",
            attachments=attachments or None,
        )
    except Exception as e:
        logger.warning("support ticket email failed: %s", e)
    return {"message": "Issue submitted successfully", "ticket_id": ticket_id}


# /admin/disputes/{dispute_id}/resolve moved to routers/admin.py (Phase D).
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
# /admin/interview-bookings moved to routers/admin.py (Phase D).
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
# /admin/redemption-requests moved to routers/admin.py (Phase D).
# /admin/redemption-requests/{req_id}/approve moved to routers/admin.py (Phase D).
# /admin/redemption-requests/{req_id}/mark-paid moved to routers/admin.py (Phase D).
# /admin/redemption-requests/{req_id}/reject moved to routers/admin.py (Phase D).
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


# /admin/users/{user_id} moved to routers/admin.py (Phase D).
# ---- Adjust Credits ----
class AdminCreditAdjustBody(BaseModel):
    delta: int = Field(..., description="Positive to add, negative to remove")
    reason: str = Field(min_length=2, max_length=400)


# /admin/users/{user_id}/credits/adjust moved to routers/admin.py (Phase D).
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


# /admin/interviews/bookings/{booking_id}/cancel moved to routers/admin.py (Phase D).
# ---- List Audit Logs ----
# /admin/audit-logs moved to routers/admin.py (Phase D).
# /admin/interviews/slots/{slot_id}/cancel-booking moved to routers/admin.py (Phase D).
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


# /admin/export/users moved to routers/admin.py (Phase D).
# /admin/export/jobs moved to routers/admin.py (Phase D).
# /admin/export/interviews moved to routers/admin.py (Phase D).
# /admin/export/transactions moved to routers/admin.py (Phase D).
# /admin/export/redemptions moved to routers/admin.py (Phase D).
# ---- Admin Job Verification (proof of opening) ----
class AdminVerifyJobBody(BaseModel):
    decision: Literal["verified", "rejected"]
    note: Optional[str] = ""


# /admin/jobs/{job_id}/verify moved to routers/admin.py (Phase D).
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
# Phase D: admin endpoints (/admin/*)
from routers import admin as _admin_router  # noqa: E402
api.include_router(_admin_router.router)
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
