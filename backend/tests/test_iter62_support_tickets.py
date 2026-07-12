"""Iteration 62 — Raise an Issue Support Enhancement (backend).

Coverage:
  1. POST /api/support/tickets happy-path — 200 + ticket_id, row persisted with
     user_id/user_email/user_role/status='open'/has_attachment/created_at.
  2. Validation — subject < 3 chars → 400 with exact spec message; description < 5
     chars → 400 with exact spec message. No row persisted.
  3. Attachment path — small base64 stores has_attachment=true + filename.
     Malformed base64 → 400 spec message. > 5 MB decoded → 400 spec message.
  4. Auth — 401 without token; works for student, professional AND admin.
  5. Regression smoke — /api/disputes (POST+GET), /api/notifications GET,
     /api/auth/me, /api/wallet, /api/jobs listing.
"""
import base64
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = None
fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
if fe_env.exists():
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PW = "Admin@12345"


def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ---------------------------- Fixtures ----------------------------
@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ["MONGO_URL"])
    yield mc[os.environ["DB_NAME"]]
    mc.close()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _signup(role: str, prefix: str):
    domain = "acmecorp.io" if role == "professional" else "referme.io"
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "password": pw, "role": role, "name": f"{prefix} {role}"},
                      timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    assert otp, f"mock_otp missing in signup response: {r.json()}"
    v = requests.post(f"{API}/auth/verify-otp",
                      json={"email": email, "otp": otp, "purpose": "verify_email"},
                      timeout=30)
    assert v.status_code == 200, v.text
    data = v.json()
    return {
        "email": email, "pw": pw,
        "token": data["token"], "user": data["user"],
        "id": data["user"]["id"], "role": role,
    }


@pytest.fixture(scope="module")
def student():
    return _signup("student", "iter62_stud")


@pytest.fixture(scope="module")
def pro():
    return _signup("professional", "iter62_pro")


# ============================================================
# 1) Happy path — POST /support/tickets returns 200 + persists row
# ============================================================
class TestSupportTicketHappyPath:
    def test_create_ticket_student_persists_row(self, student, mongo):
        body = {
            "subject": "Cannot open notifications screen",
            "description": "When I tap the bell icon the app hangs for ~10 seconds then loads.",
        }
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]), json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("message") == "Issue submitted successfully"
        assert data.get("ticket_id"), f"ticket_id missing: {data}"
        ticket_id = data["ticket_id"]

        # DB assertion — row was actually persisted
        row = mongo.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert row is not None, "support_tickets row was not persisted"
        assert row["user_id"] == student["id"]
        assert row["user_email"] == student["email"]
        assert row["user_role"] == "student"
        assert row["subject"] == body["subject"]
        assert row["description"] == body["description"]
        assert row["status"] == "open"
        assert row["has_attachment"] is False
        assert row.get("created_at"), "created_at missing"

    def test_create_ticket_professional(self, pro, mongo):
        body = {"subject": "Slot page issue", "description": "Slots disappearing sporadically."}
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(pro["token"]), json=body, timeout=30)
        assert r.status_code == 200, r.text
        row = mongo.support_tickets.find_one({"id": r.json()["ticket_id"]}, {"_id": 0})
        assert row and row["user_role"] == "professional"

    def test_create_ticket_admin(self, admin_token, mongo):
        body = {"subject": "Admin test", "description": "Support endpoint smoke as admin role."}
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(admin_token), json=body, timeout=30)
        assert r.status_code == 200, r.text
        row = mongo.support_tickets.find_one({"id": r.json()["ticket_id"]}, {"_id": 0})
        assert row and row["user_role"] == "admin"


# ============================================================
# 2) Validation
# ============================================================
class TestSupportTicketValidation:
    def test_subject_too_short(self, student, mongo):
        before = mongo.support_tickets.count_documents({"user_id": student["id"]})
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={"subject": "ab", "description": "Long enough description here."},
                          timeout=30)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Subject is mandatory (min 3 characters)."
        after = mongo.support_tickets.count_documents({"user_id": student["id"]})
        assert after == before, "No row should be inserted on validation failure"

    def test_subject_empty(self, student):
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={"subject": "", "description": "Long enough description here."},
                          timeout=30)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Subject is mandatory (min 3 characters)."

    def test_description_too_short(self, student, mongo):
        before = mongo.support_tickets.count_documents({"user_id": student["id"]})
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={"subject": "Valid Subject", "description": "abc"},
                          timeout=30)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Issue Description is mandatory (min 5 characters)."
        after = mongo.support_tickets.count_documents({"user_id": student["id"]})
        assert after == before

    def test_description_whitespace_only(self, student):
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={"subject": "Valid Subject", "description": "     "},
                          timeout=30)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Issue Description is mandatory (min 5 characters)."


# ============================================================
# 3) Attachment path
# ============================================================
class TestSupportTicketAttachment:
    def test_small_valid_attachment_stored(self, student, mongo):
        payload = base64.b64encode(b"hello world attachment").decode("ascii")
        body = {
            "subject": "With attachment",
            "description": "See attached screenshot for reference.",
            "attachment_base64": payload,
            "attachment_filename": "screenshot.png",
            "attachment_mime": "image/png",
        }
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]), json=body, timeout=30)
        assert r.status_code == 200, r.text
        row = mongo.support_tickets.find_one({"id": r.json()["ticket_id"]}, {"_id": 0})
        assert row and row["has_attachment"] is True
        assert row["attachment_filename"] == "screenshot.png"

    def test_data_uri_prefix_stripped(self, student, mongo):
        # Simulate the frontend sending a data URI as-is
        raw = base64.b64encode(b"pdf-body-content-here").decode("ascii")
        data_uri = f"data:application/pdf;base64,{raw}"
        body = {
            "subject": "Data URI attachment",
            "description": "Attaching a PDF as data URI.",
            "attachment_base64": data_uri,
            "attachment_filename": "resume.pdf",
            "attachment_mime": "application/pdf",
        }
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]), json=body, timeout=30)
        assert r.status_code == 200, r.text
        row = mongo.support_tickets.find_one({"id": r.json()["ticket_id"]}, {"_id": 0})
        assert row and row["has_attachment"] is True
        assert row["attachment_filename"] == "resume.pdf"

    def test_malformed_base64_rejected(self, student):
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={
                              "subject": "Bad attachment",
                              "description": "This should fail decoding.",
                              "attachment_base64": "!!!not-base64@@@",
                              "attachment_filename": "x.bin",
                              "attachment_mime": "application/octet-stream",
                          },
                          timeout=30)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Attachment is not a valid base64 payload."

    def test_attachment_over_5mb_rejected(self, student):
        # 6 MB of zero bytes → base64 ≈ 8 MB payload
        big = base64.b64encode(b"\x00" * (6 * 1024 * 1024)).decode("ascii")
        r = requests.post(f"{API}/support/tickets",
                          headers=_hdr(student["token"]),
                          json={
                              "subject": "Big attachment",
                              "description": "This should exceed the 5MB cap.",
                              "attachment_base64": big,
                              "attachment_filename": "big.bin",
                              "attachment_mime": "application/octet-stream",
                          },
                          timeout=60)
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Attachment exceeds 5 MB limit."


# ============================================================
# 4) Auth gating
# ============================================================
class TestSupportTicketAuth:
    def test_no_token_returns_401(self):
        r = requests.post(f"{API}/support/tickets",
                          headers={"Content-Type": "application/json"},
                          json={"subject": "Unauth", "description": "Should be blocked."},
                          timeout=30)
        assert r.status_code == 401, r.text

    def test_invalid_token_returns_401(self):
        r = requests.post(f"{API}/support/tickets",
                          headers={"Authorization": "Bearer notavalidtoken",
                                   "Content-Type": "application/json"},
                          json={"subject": "Unauth", "description": "Should be blocked."},
                          timeout=30)
        assert r.status_code == 401, r.text


# ============================================================
# 5) Regression smoke — adjacent endpoints still work
# ============================================================
class TestRegressionSmoke:
    def test_disputes_post_and_get_still_work(self, student):
        r = requests.post(f"{API}/disputes",
                          headers=_hdr(student["token"]),
                          json={"subject": "Legacy dispute",
                                "description": "Dispute endpoint should remain untouched."},
                          timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("id"), "dispute id missing"

        r2 = requests.get(f"{API}/disputes", headers=_hdr(student["token"]), timeout=30)
        assert r2.status_code == 200, r2.text
        arr = r2.json()
        assert isinstance(arr, list) and len(arr) >= 1
        assert any(d.get("subject") == "Legacy dispute" for d in arr)

    def test_notifications_get_still_works(self, student):
        r = requests.get(f"{API}/notifications",
                         headers=_hdr(student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_auth_me_student(self, student):
        r = requests.get(f"{API}/auth/me", headers=_hdr(student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # /auth/me returns nested { user: {...}, profile: {...}, ... }
        assert data.get("user", {}).get("email") == student["email"]
        assert data.get("user", {}).get("role") == "student"

    def test_auth_me_admin(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("user", {}).get("role") == "admin"

    def test_wallet_student(self, student):
        r = requests.get(f"{API}/wallet", headers=_hdr(student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        assert "credits" in r.json()

    def test_jobs_list_open(self, student):
        r = requests.get(f"{API}/jobs", headers=_hdr(student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_jobs_apply_with_complete_profile(self, mongo):
        """Smoke: /jobs/apply with a complete-profile student on a verified employer job."""
        # 1) Signup student + email verify
        s = _signup("student", "iter62_apply")
        # 2) Complete the 11 mandatory fields via PUT /profile + phone OTP
        body = {
            "name": "Test Student",
            "gender": "male",
            "dob": "2000-01-01",
            "education": "BE",
            "passed_out_year": 2022,
            "current_location": "Bangalore",
            "preferred_role": "fresher",
            "years_of_experience": 0,
            "skills": ["Python"],
            "resume_link": "https://example.com/resume.pdf",
        }
        r = requests.put(f"{API}/profile", headers=_hdr(s["token"]), json=body, timeout=30)
        assert r.status_code == 200, r.text
        r1 = requests.post(f"{API}/profile/phone/send-otp", headers=_hdr(s["token"]),
                           json={"phone": "9812345678"}, timeout=30)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/profile/phone/verify-otp", headers=_hdr(s["token"]),
                           json={"phone": r1.json()["phone"], "otp": r1.json()["mock_otp"]},
                           timeout=30)
        assert r2.status_code == 200, r2.text
        # 3) Seed a verified employer job (source != admin)
        job_id = uuid.uuid4().hex
        emp_id = "iter62-emp-" + job_id[:6]
        mongo.users.insert_one({
            "id": emp_id, "email": f"iter62-emp-{job_id[:6]}@referme.io",
            "role": "employer", "name": "Iter62 Co", "is_email_verified": True,
            "credits": 0, "profile": {"company_name": "Iter62 Co"},
            "created_at": "2025-01-01T00:00:00+00:00",
        })
        mongo.jobs.insert_one({
            "id": job_id, "employer_id": emp_id, "employer_name": "Iter62 Co",
            "posted_by_role": "employer", "posted_by_name": "Iter62 Employer",
            "source": "professional", "title": f"Iter62 Job {job_id[:6]}",
            "company": "Iter62 Co", "description": "Regression smoke apply.",
            "location": "Bangalore", "skills_required": ["Python"],
            "category": "fresher", "experience_required": 0,
            "experience_min": 0, "experience_max": 0,
            "open_positions": 1, "open_positions_label": "1",
            "status": "open", "verification_status": "verified",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        })
        # 4) Apply
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(s["token"]),
                          json={"job_id": job_id}, timeout=30)
        assert r.status_code == 200, r.text
        # Application persisted
        app = mongo.applications.find_one({"job_id": job_id, "student_id": s["id"]}, {"_id": 0})
        assert app is not None and app["status"] == "applied"

    def test_interviews_book_smoke(self, mongo):
        """Smoke: /interviews/book — student books a pro-created slot."""
        # 1) student with complete profile
        s = _signup("student", "iter62_book")
        body = {
            "name": "Test Student", "gender": "male", "dob": "2000-01-01",
            "education": "BE", "passed_out_year": 2022,
            "current_location": "Bangalore", "preferred_role": "fresher",
            "years_of_experience": 0, "skills": ["Python"],
            "resume_link": "https://example.com/resume.pdf",
        }
        assert requests.put(f"{API}/profile", headers=_hdr(s["token"]), json=body,
                            timeout=30).status_code == 200
        # Give the student enough credits for the booking
        mongo.users.update_one({"id": s["id"]}, {"$set": {"credits": 500, "free_uses_left": 0}})
        # 2) Seed a pro user + directly seed an available interview slot in mongo
        pro_id = "iter62-pro-" + uuid.uuid4().hex[:6]
        mongo.users.insert_one({
            "id": pro_id, "email": f"iter62-pro-{pro_id[-6:]}@acmecorp.io",
            "role": "professional", "name": "Iter62 Pro",
            "is_email_verified": True, "credits": 0,
            "profile": {"phone": "9876543210", "phone_verified": True, "company": "AcmeCorp"},
            "gmail_verified": True,
            "created_at": "2025-01-01T00:00:00+00:00",
        })
        slot_id = uuid.uuid4().hex
        from datetime import datetime, timedelta, timezone as _tz
        start = (datetime.now(_tz.utc) + timedelta(days=2)).replace(microsecond=0)
        end = start + timedelta(minutes=30)
        mongo.interview_slots.insert_one({
            "id": slot_id, "pro_id": pro_id, "pro_name": "Iter62 Pro",
            "skill_set": ["Python"], "language": "English",
            "start_at": start.isoformat(), "end_at": end.isoformat(),
            "status": "available", "created_at": "2025-01-01T00:00:00+00:00",
        })
        # 3) Book
        r = requests.post(f"{API}/interviews/book", headers=_hdr(s["token"]),
                          json={"slot_id": slot_id}, timeout=30)
        assert r.status_code == 200, r.text
        # Slot flipped to booked
        slot = mongo.interview_slots.find_one({"id": slot_id}, {"_id": 0})
        assert slot["status"] == "booked"
        assert slot["student_id"] == s["id"]
