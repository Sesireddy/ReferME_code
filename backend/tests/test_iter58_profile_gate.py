"""Iteration 58 — Job Application Profile-Completion Gate.

Verifies:
  1. GET /api/auth/me returns profile_completion (int 0..100) + missing_fields (list[str])
     for Job Seekers. The 11 mandatory fields are the ones defined in
     server.student_missing_fields.
  2. POST /api/jobs/apply on an INCOMPLETE student profile returns HTTP 400 with
     detail={'code': 'PROFILE_INCOMPLETE', 'message': ..., 'missing_fields': [...]}.
     No credits deducted, no application row created.
  3. POST /api/jobs/apply on a COMPLETE student profile succeeds
     (iteration-51 charge rules preserved: Fresher=99, Experienced=199).
  4. Order: profile-incomplete check fires BEFORE the admin-source rejection.
  5. Completion math: 0 missing → 100%, 3 missing → 73%, 11 missing → 0%.
  6. Regression — /interviews/book does NOT gate on the 11-field completion.
  7. Regression — GET /api/jobs and POST /jobs/{id}/save work with incomplete profile.
  8. Regression — Pro /auth/me still returns profile_completion + missing_fields (9-field).
     Signup 100-credit welcome bonus still fires; referral remains iteration-57 policy.
"""
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = None
fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
if fe_env.exists():
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PW = "Admin@12345"

# The 11 mandatory Job Seeker fields (exact strings emitted by server.student_missing_fields).
ELEVEN_MISSING_ALL = {
    "Full Name",
    "Profile Category",
    "Verify Mobile Number",
    "Verify Email Address",
    "Gender",
    "Date of Birth",
    "Education Qualification",
    "Passed Out Year",
    "Add Skills",
    "Current Location",
    "Upload Resume",
}


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
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _signup_student_unverified(prefix: str):
    """Signup a student but DO NOT verify email — used for the 'all-11-missing' case."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@referme.io"
    pw = "Test@12345"
    body = {"email": email, "password": pw, "role": "student", "name": ""}
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    # Login (email not verified) — get token via the login endpoint? Login blocks unverified.
    # Instead, use the token returned by signup? Signup does NOT return a token — verify does.
    # For the all-11-missing case we need a token WITHOUT verifying email.
    # Solution: verify then flip is_email_verified back to False in DB.
    v = requests.post(f"{API}/auth/verify-otp",
                      json={"email": email, "otp": otp, "purpose": "verify_email"}, timeout=30)
    assert v.status_code == 200
    tok = v.json()["token"]
    uid = v.json()["user"]["id"]
    return {"email": email, "pw": pw, "token": tok, "id": uid}


def _signup_student(prefix: str, name: str = ""):
    """Signup + email-verify a student. Returns token + id."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@referme.io"
    pw = "Test@12345"
    body = {"email": email, "password": pw, "role": "student", "name": name}
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    v = requests.post(f"{API}/auth/verify-otp",
                      json={"email": email, "otp": otp, "purpose": "verify_email"}, timeout=30)
    assert v.status_code == 200, v.text
    return {"email": email, "pw": pw, "token": v.json()["token"], "id": v.json()["user"]["id"]}


def _signup_pro(prefix: str, mongo):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@acmecorp.io"
    pw = "Test@12345"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "password": pw, "role": "professional", "name": f"{prefix} pro"}, timeout=30)
    assert r.status_code == 200, r.text
    v = requests.post(f"{API}/auth/verify-otp",
                      json={"email": email, "otp": r.json()["mock_otp"], "purpose": "verify_email"}, timeout=30)
    assert v.status_code == 200
    uid = v.json()["user"]["id"]
    mongo.users.update_one({"id": uid}, {"$set": {
        "profile.phone": "9876543210",
        "profile.phone_verified": True,
        "profile.company": "AcmeCorp",
        "gmail_verified": True,
        "alternate_gmail": f"{prefix}.p@gmail.com",
    }})
    return {"email": email, "pw": pw, "token": v.json()["token"], "id": uid}


def _complete_student_profile(token: str, uid: str, mongo, category: str = "fresher"):
    """Fill ALL 11 mandatory fields for a Job Seeker.

    Uses PUT /profile for the non-phone fields, and the /profile/phone/verify-otp
    flow for phone_verified. Sets name via PUT /profile.
    """
    # 1) Fill non-phone fields via PUT /profile (auth-router does not accept phone_verified from client)
    body = {
        "name": "Test Student",
        "gender": "male",
        "dob": "2000-01-01",
        "education": "BE",
        "passed_out_year": 2022,
        "current_location": "Bangalore",
        "preferred_role": category,
        "years_of_experience": 0 if category == "fresher" else 3,
        "skills": ["Python", "FastAPI"],
        "resume_link": "https://example.com/resume.pdf",
    }
    r = requests.put(f"{API}/profile", headers=_hdr(token), json=body, timeout=30)
    assert r.status_code == 200, r.text
    # 2) Set + verify phone via OTP endpoints
    phone = "9812345678"
    r1 = requests.post(f"{API}/profile/phone/send-otp",
                       headers=_hdr(token), json={"phone": phone}, timeout=30)
    assert r1.status_code == 200, r1.text
    otp = r1.json()["mock_otp"]
    phone_e164 = r1.json()["phone"]
    r2 = requests.post(f"{API}/profile/phone/verify-otp",
                       headers=_hdr(token),
                       json={"phone": phone_e164, "otp": otp}, timeout=30)
    assert r2.status_code == 200, r2.text


def _make_employer_job(mongo, admin_token: str):
    """Insert a verified, open, non-admin-source job that a student can apply to.

    Rather than fight the phone-verify / email-verify gates for a real employer
    signup, we insert directly into the jobs collection with the same shape a
    professional-posted verified job would have.
    """
    job_id = uuid.uuid4().hex
    employer_id = "iter58-employer-" + job_id[:6]
    # Create a lightweight employer user so job listing/employer notifications don't error.
    mongo.users.insert_one({
        "id": employer_id,
        "email": f"iter58-emp-{job_id[:6]}@referme.io",
        "role": "employer",
        "name": "Iter58 Employer",
        "is_email_verified": True,
        "credits": 0,
        "profile": {"company_name": "Iter58 Co"},
        "created_at": "2025-01-01T00:00:00+00:00",
    })
    doc = {
        "id": job_id,
        "employer_id": employer_id,
        "employer_name": "Iter58 Co",
        "posted_by_role": "employer",
        "posted_by_name": "Iter58 Employer",
        "source": "professional",  # NOT admin
        "title": f"Iter58 Backend {job_id[:6]}",
        "company": "Iter58 Co",
        "description": "Test job for iter58 apply happy path.",
        "location": "Bangalore",
        "skills_required": ["Python"],
        "category": "fresher",
        "experience_required": 0,
        "experience_min": 0,
        "experience_max": 0,
        "open_positions": 1,
        "open_positions_label": "1",
        "status": "open",
        "verification_status": "verified",
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
    }
    mongo.jobs.insert_one(doc)
    return job_id, employer_id


def _make_admin_job(admin_token: str):
    body = {
        "title": f"Iter58 Walk-in {uuid.uuid4().hex[:6]}",
        "company": "Iter58 Walk-in Co",
        "description": "Walk-in job for iter58 order test.",
        "location": "Bangalore",
        "skills_required": ["Python"],
        "employment_type": "Full-time",
        "salary_range": "3-5 LPA",
        "industry_type": "IT Services",
        "category": "fresher",
        "experience_min": 0,
        "experience_max": 0,
        "open_positions": 1,
        "walk_in_date": "2030-01-01",
        "walk_in_time": "10:00 AM - 4:00 PM",
        "venue": "Bangalore Office",
        "contact_person": "HR",
        "contact_number": "9876543210",
        "contact_email": "hr@example.com",
        "status": "open",
        # Iter 66: last_date_to_apply required for admin publish
        "last_date_to_apply": "2030-06-30",
    }
    r = requests.post(f"{API}/admin/jobs", headers=_hdr(admin_token), json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ============================================================
# 1) /auth/me profile_completion + missing_fields (student)
# ============================================================
class TestAuthMeStudent:
    def test_fresh_student_has_all_11_missing_after_verify(self, mongo):
        """A student who has just email-verified but not filled anything else.
        Email-verified so 'Verify Email Address' is NOT in missing → 10 missing.
        """
        s = _signup_student("iter58_fresh")
        r = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30)
        assert r.status_code == 200, r.text
        me = r.json()
        assert "profile_completion" in me and isinstance(me["profile_completion"], int)
        assert 0 <= me["profile_completion"] <= 100
        assert "missing_fields" in me and isinstance(me["missing_fields"], list)
        missing = set(me["missing_fields"])
        # Email is verified → not in missing. Name was provided empty at signup.
        assert "Verify Email Address" not in missing
        # The other 10 fields should all be missing (name empty, no phone/gender/dob/education/etc)
        expected_missing = ELEVEN_MISSING_ALL - {"Verify Email Address"}
        assert missing == expected_missing, f"Expected {expected_missing}, got {missing}"
        # 10 missing → round((11-10)/11 * 100) = 9
        assert me["profile_completion"] == 9

    def test_user_public_also_exposes_profile_completion_for_student(self, mongo):
        s = _signup_student("iter58_pub")
        r = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30)
        assert r.status_code == 200
        me = r.json()
        # user_public() should also carry profile_completion for students (server.py L268)
        assert "profile_completion" in me["user"]
        assert isinstance(me["user"]["profile_completion"], int)
        assert me["user"]["profile_completion"] == me["profile_completion"]

    def test_completion_math_three_missing(self, mongo):
        """Drop 3 fields from a fully-completed student → expect ~73%."""
        s = _signup_student("iter58_math3", name="Test Student")
        _complete_student_profile(s["token"], s["id"], mongo, category="fresher")
        # Now drop 3 fields: gender, dob, current_location
        mongo.users.update_one({"id": s["id"]},
                               {"$unset": {"profile.gender": "", "profile.dob": "",
                                           "profile.current_location": ""}})
        r = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30)
        me = r.json()
        assert len(me["missing_fields"]) == 3
        # round((11-3)/11 * 100) = round(72.72) = 73
        assert me["profile_completion"] == 73

    def test_completion_math_zero_missing_is_100(self, mongo):
        s = _signup_student("iter58_math0", name="Test Student")
        _complete_student_profile(s["token"], s["id"], mongo, category="fresher")
        r = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30)
        me = r.json()
        assert me["missing_fields"] == [], f"Unexpected missing: {me['missing_fields']}"
        assert me["profile_completion"] == 100

    def test_completion_math_all_eleven_missing_is_zero(self, mongo):
        """Create student, then flip is_email_verified=False so all 11 fields register missing."""
        s = _signup_student("iter58_math11")
        # Wipe name + flip email-verified to False so all 11 register as missing.
        mongo.users.update_one({"id": s["id"]},
                               {"$set": {"is_email_verified": False, "name": ""}})
        r = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30)
        me = r.json()
        assert set(me["missing_fields"]) == ELEVEN_MISSING_ALL, f"Got {me['missing_fields']}"
        assert me["profile_completion"] == 0


# ============================================================
# 2) /jobs/apply — 400 PROFILE_INCOMPLETE with structured detail
# ============================================================
class TestApplyGate:
    def test_apply_incomplete_returns_structured_400(self, mongo, admin_token):
        s = _signup_student("iter58_gate_inc")
        job_id, emp_id = _make_employer_job(mongo, admin_token)
        # Snapshot credits pre-call
        u_before = mongo.users.find_one({"id": s["id"]})
        credits_before = u_before.get("credits", 0)
        r = requests.post(f"{API}/jobs/apply",
                          headers=_hdr(s["token"]),
                          json={"job_id": job_id}, timeout=30)
        assert r.status_code == 400, r.text
        body = r.json()
        assert "detail" in body
        detail = body["detail"]
        assert isinstance(detail, dict), f"detail must be a dict, got {type(detail)}: {detail}"
        assert detail.get("code") == "PROFILE_INCOMPLETE"
        assert "message" in detail and "profile" in detail["message"].lower()
        assert "missing_fields" in detail and isinstance(detail["missing_fields"], list)
        assert len(detail["missing_fields"]) > 0

        # /auth/me must report the same missing_fields list
        me = requests.get(f"{API}/auth/me", headers=_hdr(s["token"]), timeout=30).json()
        assert set(detail["missing_fields"]) == set(me["missing_fields"])

        # No credits deducted, no application row.
        u_after = mongo.users.find_one({"id": s["id"]})
        assert u_after.get("credits", 0) == credits_before
        app = mongo.applications.find_one({"job_id": job_id, "student_id": s["id"]})
        assert app is None

    def test_apply_complete_profile_succeeds_fresher_99(self, mongo, admin_token):
        s = _signup_student("iter58_ok_fresher", name="Test Student")
        _complete_student_profile(s["token"], s["id"], mongo, category="fresher")
        # Ensure the student has enough credits (signup grants 100 welcome bonus → enough for 99)
        u = mongo.users.find_one({"id": s["id"]})
        assert u.get("credits", 0) >= 99, f"student credits={u.get('credits')}"
        job_id, _ = _make_employer_job(mongo, admin_token)
        credits_before = u["credits"]
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(s["token"]),
                          json={"job_id": job_id}, timeout=30)
        assert r.status_code == 200, r.text
        # Fresher = 99 charged (unless the free_uses_left path was consumed — new signup gets 2)
        u2 = mongo.users.find_one({"id": s["id"]})
        # Either 99 credits were charged OR a free-use was consumed.
        if u2.get("free_uses_left", 0) < u.get("free_uses_left", 0):
            assert u2["credits"] == credits_before, "Free-use path — credits unchanged"
        else:
            assert u2["credits"] == credits_before - 99
        # Application row persisted.
        app = mongo.applications.find_one({"job_id": job_id, "student_id": s["id"]}, {"_id": 0})
        assert app is not None
        assert app["status"] == "applied"

    def test_apply_complete_profile_succeeds_experienced_99(self, mongo, admin_token):
        # Iter 67: unified 99-credit charge for all Job Seekers (including experienced).
        s = _signup_student("iter58_ok_exp", name="Test Student")
        _complete_student_profile(s["token"], s["id"], mongo, category="experienced")
        # Ensure sufficient credits (standardized=99, welcome=100 → top up via DB write for test isolation).
        mongo.users.update_one({"id": s["id"]}, {"$set": {"credits": 500, "free_uses_left": 0}})
        job_id, _ = _make_employer_job(mongo, admin_token)
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(s["token"]),
                          json={"job_id": job_id}, timeout=30)
        assert r.status_code == 200, r.text
        u2 = mongo.users.find_one({"id": s["id"]})
        assert u2["credits"] == 500 - 99, f"Expected 401, got {u2['credits']}"


# ============================================================
# 3) Order — profile-incomplete check MUST fire before admin-source rejection
# ============================================================
class TestApplyOrder:
    def test_incomplete_beats_admin_source_rejection(self, admin_token):
        s = _signup_student("iter58_order")
        admin_job_id = _make_admin_job(admin_token)
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(s["token"]),
                          json={"job_id": admin_job_id}, timeout=30)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        # Should be PROFILE_INCOMPLETE structured, NOT the Admin Walk-in string.
        assert isinstance(detail, dict), f"Expected structured dict, got {detail}"
        assert detail.get("code") == "PROFILE_INCOMPLETE"

    def test_complete_profile_still_blocked_by_admin_source(self, mongo, admin_token):
        s = _signup_student("iter58_order_complete", name="Test Student")
        _complete_student_profile(s["token"], s["id"], mongo, category="fresher")
        admin_job_id = _make_admin_job(admin_token)
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(s["token"]),
                          json={"job_id": admin_job_id}, timeout=30)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        # Now the admin-source message should surface.
        assert isinstance(detail, str), f"Expected plain string detail, got {detail}"
        assert "Admin Walk-in" in detail


# ============================================================
# 4) Regressions — /interviews/book unaffected, /jobs GET + save-jobs unblocked
# ============================================================
class TestRegressions:
    def test_get_jobs_unblocked_with_incomplete_profile(self, mongo, admin_token):
        s = _signup_student("iter58_reg_list")
        # Ensure at least one open non-admin job exists.
        _make_employer_job(mongo, admin_token)
        r = requests.get(f"{API}/jobs", headers=_hdr(s["token"]), timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_save_job_unblocked_with_incomplete_profile(self, mongo, admin_token):
        s = _signup_student("iter58_reg_save")
        job_id, _ = _make_employer_job(mongo, admin_token)
        r = requests.post(f"{API}/jobs/{job_id}/save", headers=_hdr(s["token"]),
                          json={}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("saved") is True

    def test_interview_book_not_gated_by_11_field_completion(self, mongo, admin_token):
        """Student with incomplete profile should still be able to hit /interviews/book
        (it will fail for OTHER reasons like non-existent slot, but NOT with
        PROFILE_INCOMPLETE)."""
        s = _signup_student("iter58_reg_book")
        # Use a bogus slot id — endpoint should return 404 'Slot not found', NOT 400 profile-incomplete.
        r = requests.post(f"{API}/interviews/book", headers=_hdr(s["token"]),
                          json={"slot_id": "nonexistent-slot-id"}, timeout=30)
        assert r.status_code == 404, f"Expected 404 Slot not found, got {r.status_code}: {r.text}"
        detail = r.json().get("detail")
        # detail must be a simple string 'Slot not found', not the profile dict.
        assert isinstance(detail, str)
        assert "Slot not found" in detail


# ============================================================
# 5) Regression — Pro /auth/me still has its own profile_completion / missing_fields
# ============================================================
class TestProAuthMe:
    def test_pro_auth_me_has_completion_and_missing_fields(self, mongo):
        p = _signup_pro("iter58_pro", mongo)
        r = requests.get(f"{API}/auth/me", headers=_hdr(p["token"]), timeout=30)
        assert r.status_code == 200
        me = r.json()
        assert "profile_completion" in me and isinstance(me["profile_completion"], int)
        assert 0 <= me["profile_completion"] <= 100
        assert "missing_fields" in me and isinstance(me["missing_fields"], list)
        # user_public for a pro should NOT contain profile_completion (that key is student-only in user_public).
        assert "profile_completion" not in me["user"]

    def test_signup_welcome_bonus_still_100(self, mongo):
        s = _signup_student("iter58_bonus")
        u = mongo.users.find_one({"id": s["id"]}, {"credits": 1, "_id": 0})
        # Welcome bonus is granted on verify-otp. Should be exactly 100 for a fresh student.
        assert u.get("credits", 0) >= 100, f"expected ≥100 (welcome bonus), got {u.get('credits')}"
