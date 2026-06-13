"""
Iteration 14 backend tests:
- POST /api/jobs new fields (salary_range_label, industry_type, location_other,
  industry_other, experience_min/max, category=intern) and persistence on GET.
- Validation: industry __OTHER__ without industry_other → 400; same for location;
  experience_max < experience_min → 400.
- Legacy jobs (no new fields) survive GET with sensible defaults.
- GET /api/jobs sort=oldest order.
- GET /api/jobs?exp_min&exp_max OVERLAP match (incl. legacy fallback to experience_required).
- GET /api/jobs?category=intern filter.
- All jobs in GET /api/jobs response carry applied_count + shortlisted_count.
- Profile photo (profile_photo_base64) persists via PUT /api/profile.
"""
import os
import time
import requests
from pymongo import MongoClient

from conftest import auth_headers  # type: ignore


# ---------- helpers ----------
def _api(base_url):
    return f"{base_url}/api"


def _mark_profile_complete(user_id: str, extra: dict | None = None):
    mc = MongoClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    upd = {"profile_complete": True}
    if extra:
        upd.update(extra)
    db.users.update_one({"id": user_id}, {"$set": upd})
    mc.close()


def _post_job(api, token, **overrides):
    payload = {
        "title": "TEST_Job " + str(time.time_ns())[-6:],
        "company": "AcmeCo_TEST",
        "description": "A test job for iteration 14.",
        "location": "Bengaluru",
        "skills_required": ["Python", "FastAPI"],
        "category": "fresher",
        "open_positions_label": "1 to 5",
    }
    payload.update(overrides)
    return requests.post(f"{api}/jobs", json=payload, headers=auth_headers(token))


# ---------- Profile photo ----------
class TestProfilePhoto:
    def test_profile_photo_base64_persists(self, base_url, session, student):
        api = _api(base_url)
        # tiny base64 string
        b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9ZdNV3kAAAAASUVORK5CYII="
        r = session.put(
            f"{api}/profile",
            json={"profile_photo_base64": b64, "full_name": "Photo Tester"},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        r2 = session.get(f"{api}/auth/me", headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        data = r2.json()
        # the profile payload should include the base64 photo
        prof = data.get("profile") or data
        assert prof.get("profile_photo_base64", "").startswith("data:image/png;base64,")


# ---------- Job posting + new fields ----------
class TestJobPostingNewFields:
    def test_post_job_with_all_new_fields(self, base_url, session, professional):
        api = _api(base_url)
        _mark_profile_complete(
            professional["user"]["id"],
            {"profile": {"company_name": "AcmeCo", "current_designation": "SDE",
                          "current_location": "Bengaluru", "skills": ["Python"]}},
        )
        r = _post_job(
            api, professional["token"],
            title="TEST_Iter14_NewFields",
            location="__OTHER__",
            location_other="Goa",
            salary_range_label="5-10",
            industry_type="__OTHER__",
            industry_other="Quantum Computing",
            category="experienced",
            experience_min=3,
            experience_max=7,
            experience_required=3,
        )
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["location"] == "Goa"
        assert job["industry_type"] == "Quantum Computing"
        assert job["salary_range_label"] == "5-10"
        assert job["experience_min"] == 3
        assert job["experience_max"] == 7
        assert job["category"] == "experienced"
        jid = job["id"]
        # GET by id verifies persistence
        r2 = session.get(f"{api}/jobs/{jid}", headers=auth_headers(professional["token"]))
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["salary_range_label"] == "5-10"
        assert j2["industry_type"] == "Quantum Computing"
        assert j2["experience_min"] == 3 and j2["experience_max"] == 7

    def test_post_job_category_intern(self, base_url, session, professional):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        r = _post_job(api, professional["token"], category="intern", title="TEST_Iter14_Intern")
        assert r.status_code == 200, r.text
        assert r.json()["category"] == "intern"

    def test_post_job_industry_other_missing_specify(self, base_url, professional):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        r = _post_job(api, professional["token"], industry_type="__OTHER__")
        assert r.status_code == 400, r.text
        assert "industry" in r.json()["detail"].lower()

    def test_post_job_location_other_missing_specify(self, base_url, professional):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        r = _post_job(api, professional["token"], location="__OTHER__", location_other="")
        assert r.status_code == 400, r.text
        assert "location" in r.json()["detail"].lower()

    def test_post_job_exp_max_less_than_min(self, base_url, professional):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        r = _post_job(
            api, professional["token"],
            category="experienced",
            experience_required=3,
            experience_min=5,
            experience_max=2,
        )
        assert r.status_code == 400, r.text
        assert "experience" in r.json()["detail"].lower()


# ---------- GET /jobs sort + overlap + counts ----------
class TestJobListing:
    def test_sort_oldest_and_newest(self, base_url, session, professional, student):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        co = "AcmeSort_TEST_" + os.urandom(3).hex()
        a = _post_job(api, professional["token"], title="TEST_Iter14_Sort_A", company=co).json()
        time.sleep(1.1)
        b = _post_job(api, professional["token"], title="TEST_Iter14_Sort_B", company=co).json()

        r = session.get(f"{api}/jobs", params={"sort": "oldest", "company": co},
                        headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()]
        # A is older than B → A appears before B
        assert ids.index(a["id"]) < ids.index(b["id"])

        r2 = session.get(f"{api}/jobs", params={"sort": "newest", "company": co},
                         headers=auth_headers(student["token"]))
        ids2 = [j["id"] for j in r2.json()]
        assert ids2.index(b["id"]) < ids2.index(a["id"])

    def test_applied_and_shortlisted_counts_on_all_jobs(self, base_url, session, professional, student):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        r = session.get(f"{api}/jobs", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        jobs = r.json()
        assert len(jobs) > 0, "Need at least one job (sample seeded) for this test"
        for j in jobs:
            assert "applied_count" in j and isinstance(j["applied_count"], int)
            assert "shortlisted_count" in j and isinstance(j["shortlisted_count"], int)
            assert j["applied_count"] >= 0 and j["shortlisted_count"] >= 0

    def test_overlap_experience_filter(self, base_url, session, professional, student):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        # Job 1: 4–7  (overlaps 3-5)
        j1 = _post_job(api, professional["token"], title="TEST_Iter14_Exp_4_7",
                       category="experienced", experience_required=4,
                       experience_min=4, experience_max=7).json()
        # Job 2: 8–10 (does NOT overlap 3-5)
        j2 = _post_job(api, professional["token"], title="TEST_Iter14_Exp_8_10",
                       category="experienced", experience_required=8,
                       experience_min=8, experience_max=10).json()
        # Legacy job: only experience_required=3, no min/max in DB
        legacy = _post_job(api, professional["token"], title="TEST_Iter14_Exp_Legacy3",
                           category="experienced", experience_required=3).json()
        # Force legacy shape: null experience_min/max in DB
        mc = MongoClient(os.environ["MONGO_URL"])
        mc[os.environ["DB_NAME"]].jobs.update_one(
            {"id": legacy["id"]},
            {"$set": {"experience_min": None, "experience_max": None}},
        )
        mc.close()

        r = session.get(f"{api}/jobs", params={"exp_min": "3", "exp_max": "5"},
                        headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        ids = {j["id"] for j in r.json()}
        assert j1["id"] in ids, "Job 4-7 must overlap with filter 3-5"
        assert j2["id"] not in ids, "Job 8-10 must NOT match filter 3-5"
        assert legacy["id"] in ids, "Legacy exp=3 must match filter 3-5"

    def test_category_intern_filter(self, base_url, session, professional, student):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        intern_job = _post_job(api, professional["token"], title="TEST_Iter14_Intern_Filter",
                                category="intern").json()
        fresher_job = _post_job(api, professional["token"], title="TEST_Iter14_Fresher_Filter",
                                 category="fresher").json()
        r = session.get(f"{api}/jobs", params={"category": "intern"},
                        headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        ids = {j["id"] for j in r.json()}
        assert intern_job["id"] in ids
        assert fresher_job["id"] not in ids
        for j in r.json():
            assert j["category"] == "intern"


# ---------- Regression: legacy jobs survive GET ----------
class TestLegacyJobsCompat:
    def test_legacy_job_no_new_fields_returned_safely(self, base_url, session, professional, student):
        api = _api(base_url)
        _mark_profile_complete(professional["user"]["id"])
        # Insert a "legacy" job directly into the DB without new fields
        mc = MongoClient(os.environ["MONGO_URL"])
        db = mc[os.environ["DB_NAME"]]
        legacy_id = "test_iter14_legacy_" + os.urandom(4).hex()
        legacy_co = "LegacyCo_" + os.urandom(3).hex()
        db.jobs.insert_one({
            "id": legacy_id,
            "employer_id": professional["user"]["id"],
            "employer_name": legacy_co,
            "posted_by_role": "professional",
            "posted_by_name": "Tester",
            "title": "TEST_Iter14_LegacyOnly",
            "company": legacy_co,
            "description": "Legacy job no new fields",
            "location": "Bengaluru",
            "skills_required": ["Python"],
            "category": "fresher",
            "experience_required": 0,
            "open_positions": 5,
            "open_positions_label": "1 to 5",
            "status": "open",
            "created_at": "2025-01-01T00:00:00+00:00",
        })
        mc.close()

        r = session.get(f"{api}/jobs", params={"company": legacy_co},
                        headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        match = next((j for j in r.json() if j["id"] == legacy_id), None)
        assert match is not None, "Legacy job must surface in GET /jobs"
        assert "applied_count" in match and "shortlisted_count" in match


# ---------- Smoke regression: auth & profile ----------
class TestSmokeRegression:
    def test_auth_login_admin(self, base_url, session):
        api = _api(base_url)
        r = session.post(f"{api}/auth/login",
                         json={"email": "admin@referme.app", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        assert "token" in r.json()

    def test_leaderboard_runs(self, base_url, session, student):
        api = _api(base_url)
        r = session.get(f"{api}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code in (200, 404)  # depending on data, may be empty
