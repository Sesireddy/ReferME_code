"""Iter 31 — Resend email-provider migration regression.

Validates that all transactional email paths now route through Resend
(formerly SendGrid). We inspect /var/log/supervisor/backend.err.log for
the expected `Resend OK to=... subject=... id=...` log line emitted by
server.send_html_email() after each auth/booking endpoint call.

Endpoints covered:
- POST /api/auth/signup            (verify_email OTP)
- POST /api/auth/verify-otp        (no email, but unblocks signup chain)
- POST /api/auth/forgot-password   (reset_password OTP)
- POST /api/auth/reset-password    (no email, completes flow)
- POST /api/auth/login             (no email, sanity)
- POST /api/interviews/book        (booking confirmation x2 + .ics)

Also confirms backend boots cleanly: /api/auth/me returns 401 (mounted),
not 404, and no NameError/ImportError appears in stdout since startup.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

# ----------------------------- env / constants -----------------------------
BACKEND_LOG = "/var/log/supervisor/backend.err.log"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or ""
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


# ----------------------------- helpers -----------------------------
def _log_tail(lines: int = 400) -> str:
    try:
        with open(BACKEND_LOG, "r", errors="ignore") as f:
            data = f.read().splitlines()[-lines:]
        return "\n".join(data)
    except FileNotFoundError:
        return ""


def _log_mark() -> int:
    """Return current line count in the backend log so callers can scan only NEW lines."""
    try:
        with open(BACKEND_LOG, "r", errors="ignore") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _log_new(mark: int) -> str:
    try:
        with open(BACKEND_LOG, "r", errors="ignore") as f:
            return "\n".join(f.read().splitlines()[mark:])
    except FileNotFoundError:
        return ""


def _wait_log_match(mark: int, needle: str, timeout: float = 5.0) -> str:
    """Poll the backend log for `needle` to appear AFTER position `mark`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = _log_new(mark)
        if needle in chunk:
            return chunk
        time.sleep(0.25)
    return _log_new(mark)


# Use Resend's test inbox so we don't bill / spam real addresses but still
# exercise the live API path.
def _resend_email(role: str) -> str:
    return f"delivered+iter31_{role}_{uuid.uuid4().hex[:6]}@resend.dev"


@pytest.fixture(scope="session")
def http() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


# ============================================================================
# Module 1 — backend boots cleanly
# ============================================================================
class TestBackendBoot:
    def test_api_mounted_not_404(self, http):
        # /docs is intentionally disabled in some envs; use a known protected route.
        r = http.get(f"{API}/auth/me")
        assert r.status_code == 401, f"expected 401 Unauthorized, got {r.status_code} {r.text[:200]}"

    def test_no_import_or_name_errors_since_startup(self):
        log = _log_tail(2000)
        # Find the LAST 'Application startup complete' marker and scan only AFTER it.
        idx = log.rfind("Application startup complete")
        scan = log[idx:] if idx >= 0 else log
        for bad in ("NameError", "ImportError", "_can_use_free"):
            # _can_use_free is fine as a normal symbol, but never as part of an error trace.
            if bad in ("NameError", "ImportError"):
                assert bad not in scan, f"backend log contains {bad} after startup:\n{scan[-500:]}"


# ============================================================================
# Module 2 — signup / verify-otp via Resend
# ============================================================================
class TestSignupViaResend:
    def test_signup_returns_otp_and_logs_resend_ok(self, http):
        email = _resend_email("student")
        mark = _log_mark()
        r = http.post(
            f"{API}/auth/signup",
            json={"email": email, "password": "Test@12345", "role": "student", "name": "TEST Student"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "mock_otp" in body, f"expected mock_otp in response (TEST_RETURN_OTP=1), got {body}"
        assert len(body["mock_otp"]) == 6 and body["mock_otp"].isdigit()
        assert body.get("email_sent") is True, f"email_sent must be True (Resend delivered), got {body}"

        # Resend log line MUST appear
        chunk = _wait_log_match(mark, f"Resend OK to={email}", timeout=8)
        assert f"Resend OK to={email}" in chunk, f"missing Resend log; backend lines:\n{chunk}"
        assert "SendGrid send failed" not in chunk, f"SendGrid should NOT have been tried:\n{chunk}"

        # stash for verify step
        pytest.STUDENT_EMAIL = email
        pytest.STUDENT_OTP = body["mock_otp"]

    def test_verify_otp_returns_token(self, http):
        email = getattr(pytest, "STUDENT_EMAIL", None)
        otp = getattr(pytest, "STUDENT_OTP", None)
        assert email and otp, "signup test must run first"
        r = http.post(
            f"{API}/auth/verify-otp",
            json={"email": email, "otp": otp, "purpose": "verify_email"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
        assert "user" in data and data["user"]["email"] == email
        assert data["user"]["is_email_verified"] is True
        pytest.STUDENT_TOKEN = data["token"]
        pytest.STUDENT_ID = data["user"]["id"]


# ============================================================================
# Module 3 — forgot-password / reset-password / login via Resend
# ============================================================================
class TestForgotResetViaResend:
    def test_forgot_password_logs_resend_ok(self, http):
        email = getattr(pytest, "STUDENT_EMAIL", None)
        assert email, "signup test must run first"
        mark = _log_mark()
        r = http.post(f"{API}/auth/forgot-password", json={"email": email})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "mock_otp" in body, f"TEST_RETURN_OTP echo missing in forgot response: {body}"
        pytest.RESET_OTP = body["mock_otp"]

        chunk = _wait_log_match(mark, f"Resend OK to={email}", timeout=8)
        assert f"Resend OK to={email}" in chunk, f"missing Resend log for forgot:\n{chunk}"
        assert "Password Reset Code" in chunk, f"subject should be password-reset:\n{chunk}"
        assert "SendGrid send failed" not in chunk

    def test_reset_password_and_login_with_new_pw(self, http):
        email = pytest.STUDENT_EMAIL
        otp = pytest.RESET_OTP
        new_pw = "NewPw@67890"
        r = http.post(
            f"{API}/auth/reset-password",
            json={"email": email, "otp": otp, "new_password": new_pw},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("message") == "Password reset successful"

        # Old password must now fail
        r_old = http.post(f"{API}/auth/login", json={"email": email, "password": "Test@12345"})
        assert r_old.status_code in (400, 401), f"old password should fail, got {r_old.status_code}"

        # New password must work
        r_new = http.post(f"{API}/auth/login", json={"email": email, "password": new_pw})
        assert r_new.status_code == 200, r_new.text
        data = r_new.json()
        assert "token" in data and data["user"]["email"] == email
        pytest.STUDENT_TOKEN = data["token"]  # refresh

    def test_forgot_unknown_email_does_not_leak(self, http):
        # Non-existing email: should still return 200, no mock_otp, and NOT hit Resend.
        mark = _log_mark()
        r = http.post(f"{API}/auth/forgot-password", json={"email": "nobody_iter31@example.com"})
        assert r.status_code == 200
        body = r.json()
        assert "mock_otp" not in body, f"non-existent users must not get mock_otp leak: {body}"
        # And no Resend send should fire for an unknown account
        time.sleep(1.0)
        chunk = _log_new(mark)
        assert "Resend OK to=nobody_iter31@example.com" not in chunk


# ============================================================================
# Module 4 — Phase B regression: interview booking emails go via Resend
# ============================================================================
class TestBookingEmailsViaResend:
    @pytest.fixture(scope="class")
    def pro_and_slot(self, http, mongo):
        # 1. Signup professional with a company-domain email
        pro_email = f"test_pro_iter31_{uuid.uuid4().hex[:6]}@acmecorp.io"
        pro_pw = "Test@12345"
        r = http.post(
            f"{API}/auth/signup",
            json={"email": pro_email, "password": pro_pw, "role": "professional", "name": "TEST Pro"},
        )
        assert r.status_code == 200, r.text
        otp = r.json()["mock_otp"]
        r2 = http.post(
            f"{API}/auth/verify-otp",
            json={"email": pro_email, "otp": otp, "purpose": "verify_email"},
        )
        assert r2.status_code == 200, r2.text
        pro_token = r2.json()["token"]
        pro_id = r2.json()["user"]["id"]

        # 2. Force phone_verified + gmail_verified directly in DB (the iter27 phone-gate
        #    and iter15 gmail-gate must be satisfied before creating slots).
        mongo.users.update_one(
            {"id": pro_id},
            {
                "$set": {
                    "gmail_verified": True,
                    "alternate_gmail": f"test.pro.{pro_id[:6]}@gmail.com",
                    "profile.phone_verified": True,
                    "profile.phone_verified_at": datetime.now(timezone.utc).isoformat(),
                    "profile.phone": "+919999900000",
                }
            },
        )

        # 3. Create a future slot (30 min) — book endpoint will pick the first sub-slot.
        start = (datetime.now(timezone.utc) + timedelta(days=3, hours=2)).replace(microsecond=0, second=0)
        end = start + timedelta(minutes=30)
        r3 = http.post(
            f"{API}/interviews/slots",
            json={
                "start_at": start.isoformat().replace("+00:00", "Z"),
                "end_at": end.isoformat().replace("+00:00", "Z"),
                "skill_set": ["python"],
                "experience_years": 3,
                "topic": "Backend",
            },
            headers={"Authorization": f"Bearer {pro_token}", "Content-Type": "application/json"},
        )
        assert r3.status_code == 200, f"slot create failed: {r3.status_code} {r3.text}"
        slot_id = r3.json()["id"]

        yield {"pro_email": pro_email, "pro_id": pro_id, "slot_id": slot_id}

        # cleanup
        mongo.interview_slots.delete_many({"pro_id": pro_id})
        mongo.interview_bookings.delete_many({"pro_id": pro_id})
        mongo.users.delete_one({"id": pro_id})

    def test_book_emits_two_resend_ok_lines(self, http, pro_and_slot, mongo):
        # Signup a fresh student with enough credits (signup_bonus = 100 ≥ 49 cost).
        stu_email = f"test_stu_iter31_{uuid.uuid4().hex[:6]}@resend.dev"
        stu_pw = "Test@12345"
        r = http.post(
            f"{API}/auth/signup",
            json={"email": stu_email, "password": stu_pw, "role": "student", "name": "TEST Stu"},
        )
        assert r.status_code == 200, r.text
        otp = r.json()["mock_otp"]
        r2 = http.post(
            f"{API}/auth/verify-otp",
            json={"email": stu_email, "otp": otp, "purpose": "verify_email"},
        )
        assert r2.status_code == 200, r2.text
        stu_token = r2.json()["token"]
        stu_id = r2.json()["user"]["id"]

        mark = _log_mark()
        r3 = http.post(
            f"{API}/interviews/book",
            json={"slot_id": pro_and_slot["slot_id"]},
            headers={"Authorization": f"Bearer {stu_token}", "Content-Type": "application/json"},
        )
        assert r3.status_code == 200, f"book failed: {r3.status_code} {r3.text}"

        # Two confirmation emails (student + pro) should both go via Resend.
        chunk = _wait_log_match(mark, "Resend OK to=", timeout=10)
        # Count Resend OK occurrences in the new window
        ok_count = chunk.count("Resend OK to=")
        assert ok_count >= 2, (
            f"expected 2 'Resend OK' lines (student+pro booking confirmations), got {ok_count}.\n"
            f"Backend log slice:\n{chunk}"
        )
        assert f"Resend OK to={stu_email}" in chunk, f"student confirmation missing:\n{chunk}"
        assert f"Resend OK to={pro_and_slot['pro_email']}" in chunk, f"pro confirmation missing:\n{chunk}"
        assert "Mock Interview" in chunk
        assert "SendGrid send failed" not in chunk

        # cleanup student
        mongo.users.delete_one({"id": stu_id})


# ============================================================================
# Module 5 — sanity: admin login still works (regression for previously-passing path)
# ============================================================================
class TestAdminLoginRegression:
    def test_admin_login_200(self, http):
        r = http.post(
            f"{API}/auth/login",
            json={"email": "admin@referme.app", "password": "Admin@12345"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert "token" in data
