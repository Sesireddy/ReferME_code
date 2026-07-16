"""Iteration 66 — Multi-Location + Last Date to Apply on Job Posting.

Backend tests covering the 12 cases in the review request:
  1. Pro creates job with locations=[BLR,HYD,CHN] + deadline today+7 → 200.
  2. Pro creates job with legacy location="Pune" (no locations array) → 200, locations==["Pune"].
  3. Pro creates job with locations=[] → 400 "select at least one Location".
  4. Pro creates job without last_date_to_apply → 400 mentions "Last Date to Apply".
  5. Pro creates job with last_date_to_apply=yesterday → 400 "cannot be earlier than today's".
  6. Duplicate locations dedupe case-insensitive → 200 length==1.
  7. GET /api/jobs?location=Hyderabad — returns both multi-loc and legacy jobs.
  8. Student applies to job with deadline yesterday (backdated in DB) → 400 "Applications Closed" + is_closed==true.
  9. Student applies to job with deadline tomorrow → 200.
 10. Admin creates job with locations=[Mumbai,Pune] + deadline today+30 → 200; student sees under source=admin.
 11. Admin creates draft with no last_date_to_apply → 200 allowed.
 12. Admin publishes open without deadline → 400.
"""
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from passlib.context import CryptContext
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://refer-connect-11.preview.emergentagent.com"
API = BASE.rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

TODAY = date.today()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
IN_7 = (TODAY + timedelta(days=7)).isoformat()
IN_30 = (TODAY + timedelta(days=30)).isoformat()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


# ------------ Fixtures ------------
@pytest.fixture(scope="module")
def pro_token():
    """Signup a Working Professional, verify email + directly set phone_verified in DB."""
    email = f"test_pro_iter66_{uuid.uuid4().hex[:8]}@acmecorp.io"
    password = "Test@12345"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": password, "role": "professional", "name": "Iter66 Pro"
    })
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    assert otp
    r2 = requests.post(f"{API}/auth/verify-otp", json={
        "email": email, "otp": otp, "purpose": "verify_email"
    })
    assert r2.status_code == 200, r2.text
    data = r2.json()
    uid = data["user"]["id"]
    # Flip phone_verified + basic profile so require_phone_verified passes.
    db = _mongo()
    db.users.update_one({"id": uid}, {"$set": {
        "profile.phone": "+919876543210",
        "profile.phone_verified": True,
        "profile.phone_verified_at": "2026-01-01T00:00:00+00:00",
        "profile.company_name": "Acme Iter66",
    }})
    return {"token": data["token"], "user_id": uid, "email": email}


@pytest.fixture(scope="module")
def student_token():
    """Signup a Job Seeker with complete profile so /jobs/apply passes profile gate."""
    email = f"test_student_iter66_{uuid.uuid4().hex[:8]}@example.com"
    password = "Test@12345"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": password, "role": "student", "name": "Iter66 Student"
    })
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    r2 = requests.post(f"{API}/auth/verify-otp", json={
        "email": email, "otp": otp, "purpose": "verify_email"
    })
    assert r2.status_code == 200, r2.text
    data = r2.json()
    uid = data["user"]["id"]
    # Complete profile so profile_complete passes + student_missing_fields is empty.
    db = _mongo()
    db.users.update_one({"id": uid}, {"$set": {
        "is_email_verified": True,
        "profile_complete": True,
        "credits": 100000,  # plenty for applies
        "profile": {
            "phone": "+919876543211",
            "phone_verified": True,
            "phone_verified_at": "2026-01-01T00:00:00+00:00",
            "gender": "male",
            "dob": "2000-01-01",
            "education": "B.Tech",
            "passed_out_year": 2022,
            "current_location": "Hyderabad",
            "preferred_role": "fresher",
            "skills": ["python", "fastapi"],
            "resume_link": "https://example.com/resume.pdf",
            "resume_base64": "",
        },
    }})
    return {"token": data["token"], "user_id": uid, "email": email}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ------------ Helper payloads ------------
def _pro_payload(**overrides):
    base = {
        "title": "Backend Engineer",
        "company": "Acme Iter66",
        "description": "We are hiring backend engineers for our team.",
        "skills_required": ["python", "fastapi"],
        "category": "fresher",
        "open_positions_label": "1",
        "proof_link": "https://example.com/job/opening/12345",
        "salary_range_label": "3-5",
    }
    base.update(overrides)
    return base


# ============================================================
# CASES
# ============================================================
class TestIter66Pro:
    """Cases 1–6 & 8–9 — Professional-posted jobs."""

    def test_01_multi_location_ok(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(
                locations=["Bangalore", "Hyderabad", "Chennai"],
                last_date_to_apply=IN_7,
            ),
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["locations"] == ["Bangalore", "Hyderabad", "Chennai"], j
        assert j["location"] == "Bangalore", j
        assert j["is_closed"] is False, j
        assert j["last_date_to_apply"] == IN_7
        # Stash for downstream case 7
        pytest.iter66_multi_job_id = j["id"]

    def test_02_legacy_location_only(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(location="Pune", last_date_to_apply=IN_7),
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["locations"] == ["Pune"], j
        assert j["location"] == "Pune"
        assert j["is_closed"] is False

    def test_03_empty_locations_rejected(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(locations=[], last_date_to_apply=IN_7),
        )
        assert r.status_code == 400, r.text
        detail = str(r.json().get("detail", "")).lower()
        assert "at least one location" in detail, r.text

    def test_04_missing_deadline_rejected(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(locations=["Bangalore"]),
        )
        assert r.status_code == 400, r.text
        detail = str(r.json().get("detail", ""))
        assert "Last Date to Apply" in detail, r.text

    def test_05_yesterday_deadline_rejected(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(locations=["Bangalore"], last_date_to_apply=YESTERDAY),
        )
        assert r.status_code == 400, r.text
        detail = str(r.json().get("detail", "")).lower()
        assert "earlier than today" in detail, r.text

    def test_06_duplicate_locations_dedup(self, pro_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(
                locations=["Bangalore", "bangalore", "BANGALORE"],
                last_date_to_apply=IN_7,
            ),
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["locations"]) == 1, j
        assert j["locations"][0].lower() == "bangalore"


class TestIter66FiltersAndApply:
    """Cases 7, 8, 9 — GET filter + apply gates."""

    def test_07_get_jobs_by_location_hyderabad(self, pro_token, student_token):
        db = _mongo()
        # Pro-posted jobs start with verification_status="pending" (admin approval flow).
        # Students only see verified pro jobs, so we bump the multi-loc job from case #1
        # to `verified` to reflect the real end-to-end state referenced by the review spec.
        multi_id = getattr(pytest, "iter66_multi_job_id", None)
        assert multi_id, "case #1 must have run first"
        db.jobs.update_one(
            {"id": multi_id},
            {"$set": {"verification_status": "verified"}},
        )
        # Seed a legacy-only job directly in DB (no `locations` array, only `location`).
        legacy_id = f"test-legacy-hyd-{uuid.uuid4().hex[:8]}"
        db.jobs.insert_one({
            "id": legacy_id,
            "employer_id": pro_token["user_id"],
            "employer_name": "Acme Iter66",
            "posted_by_role": "professional",
            "posted_by_name": "Iter66 Pro",
            "source": "professional",
            "title": "Legacy Hyd Job",
            "company": "Acme Iter66",
            "description": "Legacy row without locations[] and without last_date_to_apply.",
            "location": "Hyderabad",  # legacy single string ONLY
            "skills_required": ["python"],
            "category": "fresher",
            "experience_required": 0,
            "open_positions": 1,
            "open_positions_label": "1",
            "status": "open",
            "verification_status": "verified",
            "verified_by": "system",
            "verified_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        })

        r = requests.get(
            f"{API}/jobs?location=Hyderabad",
            headers=_hdr(student_token["token"]),
        )
        assert r.status_code == 200, r.text
        jobs = r.json()
        ids = {j["id"] for j in jobs}
        assert legacy_id in ids, "legacy job with only `location` field must surface"
        assert getattr(pytest, "iter66_multi_job_id", None) in ids, "multi-location job must surface"
        # Also verify annotations exist on responses.
        for j in jobs:
            if j["id"] == legacy_id:
                assert j["locations"] == ["Hyderabad"], j
                assert j["is_closed"] is False, j  # missing deadline → not closed
                break

    def test_08_apply_closed_when_deadline_passed(self, pro_token, student_token):
        # Create a job with deadline tomorrow, then backdate to yesterday in DB.
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(
                title="Closed Deadline Job",
                locations=["Bangalore"],
                last_date_to_apply=TOMORROW,
            ),
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # Backdate the deadline directly in DB.
        _mongo().jobs.update_one(
            {"id": job_id},
            {"$set": {"last_date_to_apply": YESTERDAY}},
        )
        # is_closed via GET
        r2 = requests.get(f"{API}/jobs/{job_id}", headers=_hdr(student_token["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["is_closed"] is True, r2.text
        # Apply must fail
        r3 = requests.post(
            f"{API}/jobs/apply",
            headers=_hdr(student_token["token"]),
            json={"job_id": job_id},
        )
        assert r3.status_code == 400, r3.text
        detail = str(r3.json().get("detail", "")).lower()
        assert "applications closed" in detail, r3.text

    def test_09_apply_ok_when_deadline_future(self, pro_token, student_token):
        r = requests.post(
            f"{API}/jobs",
            headers=_hdr(pro_token["token"]),
            json=_pro_payload(
                title="Open Deadline Job",
                locations=["Hyderabad"],
                last_date_to_apply=TOMORROW,
            ),
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        r2 = requests.post(
            f"{API}/jobs/apply",
            headers=_hdr(student_token["token"]),
            json={"job_id": job_id},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("message") == "Applied", body


class TestIter66Admin:
    """Cases 10–12 — Admin-posted jobs."""

    def _admin_payload(self, **overrides):
        base = {
            "company": "Iter66 Admin Co",
            "title": "Walk-in Drive",
            "description": "Walk-in drive for freshers/experienced. Bring resume.",
            "skills_required": ["communication"],
            "open_positions": 5,
            "employment_type": "Walk-in Drive",
        }
        base.update(overrides)
        return base

    def test_10_admin_multi_location_ok(self, admin_token, student_token):
        r = requests.post(
            f"{API}/admin/jobs",
            headers=_hdr(admin_token),
            json=self._admin_payload(
                locations=["Mumbai", "Pune"],
                last_date_to_apply=IN_30,
                status="open",
            ),
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["locations"] == ["Mumbai", "Pune"], j
        assert j["location"] == "Mumbai"
        assert j["last_date_to_apply"] == IN_30
        assert j["source"] == "admin"
        assert j["status"] == "open"
        job_id = j["id"]
        # Student can see it under source=admin
        r2 = requests.get(
            f"{API}/jobs?source=admin",
            headers=_hdr(student_token["token"]),
        )
        assert r2.status_code == 200, r2.text
        ids = {x["id"] for x in r2.json()}
        assert job_id in ids

    def test_11_admin_draft_no_deadline_ok(self, admin_token):
        r = requests.post(
            f"{API}/admin/jobs",
            headers=_hdr(admin_token),
            json=self._admin_payload(
                locations=["Mumbai"],
                status="draft",
                # NO last_date_to_apply
            ),
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "draft"
        assert j["last_date_to_apply"] == "" or j["last_date_to_apply"] is None

    def test_12_admin_publish_without_deadline_rejected(self, admin_token):
        r = requests.post(
            f"{API}/admin/jobs",
            headers=_hdr(admin_token),
            json=self._admin_payload(
                locations=["Mumbai"],
                status="open",
                # NO last_date_to_apply → must 400
            ),
        )
        assert r.status_code == 400, r.text
        detail = str(r.json().get("detail", ""))
        assert "Last Date to Apply" in detail, r.text


# ------------ Cleanup ------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    db = _mongo()
    # Delete users we created (email prefix)
    users_to_delete = list(db.users.find(
        {"email": {"$regex": r"^test_(pro|student)_iter66_", "$options": "i"}},
        {"id": 1},
    ))
    uids = [u["id"] for u in users_to_delete]
    if uids:
        db.jobs.delete_many({"employer_id": {"$in": uids}})
        db.applications.delete_many({"student_id": {"$in": uids}})
        db.users.delete_many({"id": {"$in": uids}})
    # Delete legacy test job + iter66-admin jobs
    db.jobs.delete_many({"id": {"$regex": r"^test-legacy-hyd-"}})
    db.jobs.delete_many({"company": "Iter66 Admin Co"})
