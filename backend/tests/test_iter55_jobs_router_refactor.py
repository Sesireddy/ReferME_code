"""Iteration 55 — Phase C part 3 refactor regression tests.

Verifies /app/backend/routers/jobs.py extraction (20 endpoints) preserved
behaviour. Scoped to regression (mechanical move) — business-logic assertions
covered in earlier iterations are not re-run here.
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
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PW = "Admin@12345"
REDEEM_PRO_EMAIL = "redeem.pro@example.com"
REDEEM_PRO_PW = "RedeemPro@12345"


def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)


def _signup(role, prefix, domain="example.com"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    body = {"email": email, "password": pw, "role": role, "name": f"{prefix} user"}
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    return email, pw, r


def _verify(email, otp):
    return requests.post(f"{API}/auth/verify-otp",
                         json={"email": email, "otp": otp, "purpose": "verify_email"},
                         timeout=30)


def _signup_verified_student(prefix, mongo=None, mark_experienced=False):
    email, pw, r = _signup("student", prefix)
    assert r.status_code == 200, r.text
    v = _verify(email, r.json()["mock_otp"])
    assert v.status_code == 200
    tok = v.json()["token"]
    user_id = v.json()["user"]["id"]
    if mongo is not None and mark_experienced:
        mongo.users.update_one(
            {"id": user_id},
            {"$set": {"profile.preferred_role": "experienced",
                      "profile.years_of_experience": 3}}
        )
    return {"email": email, "pw": pw, "token": tok, "id": user_id}


def _signup_verified_pro(prefix, mongo, phone_verified=True):
    email, pw, r = _signup("professional", prefix, domain="acmecorp.io")
    assert r.status_code == 200, r.text
    v = _verify(email, r.json()["mock_otp"])
    tok = v.json()["token"]
    uid = v.json()["user"]["id"]
    if phone_verified:
        mongo.users.update_one(
            {"id": uid},
            {"$set": {"profile.phone": "9876543210",
                      "profile.phone_verified": True,
                      "profile.company": "AcmeCorp"}}
        )
    return {"email": email, "pw": pw, "token": tok, "id": uid}


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ["MONGO_URL"])
    yield mc[os.environ["DB_NAME"]]
    mc.close()


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PW)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_a(mongo):
    return _signup_verified_pro("iter55proA", mongo)


@pytest.fixture(scope="module")
def pro_b(mongo):
    return _signup_verified_pro("iter55proB", mongo)


@pytest.fixture(scope="module")
def student_fresher(mongo):
    return _signup_verified_student("iter55stf", mongo)


@pytest.fixture(scope="module")
def student_exp(mongo):
    return _signup_verified_student("iter55ste", mongo, mark_experienced=True)


def _valid_job_body(**overrides):
    from datetime import date, timedelta
    body = {
        "title": "Iter55 Backend Engineer",
        "description": "Build APIs and stuff",
        "location": "Bangalore",
        "skills_required": ["Python", "FastAPI"],
        "company": "AcmeCorp",
        "salary_range": "10-15 LPA",
        "industry_type": "IT Services",
        "experience_required": 2,
        "open_positions_label": "1",
        "category": "experienced",
        "proof_link": "https://example.com/job",
        # Iter 66: last_date_to_apply now required for new posts
        "last_date_to_apply": (date.today() + timedelta(days=30)).isoformat(),
    }
    body.update(overrides)
    return body


# ---------------- POST /api/jobs (validation) ----------------
class TestJobCreateValidation:
    def test_missing_title_400(self, pro_a):
        b = _valid_job_body(title="")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Job Title is required" in r.text

    def test_missing_description_400(self, pro_a):
        b = _valid_job_body(description="")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Job Description is required" in r.text

    def test_missing_location_400(self, pro_a):
        b = _valid_job_body(location="")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Location is required" in r.text

    def test_missing_skills_400(self, pro_a):
        b = _valid_job_body(skills_required=[])
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Skill Set is required" in r.text

    def test_invalid_open_positions_label_400(self, pro_a):
        b = _valid_job_body(open_positions_label="999xx")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Invalid Number of Open Positions" in r.text

    def test_pro_missing_proof_400(self, pro_a):
        b = _valid_job_body(proof_link="", proof_screenshot_b64="")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 400
        assert "Job Opening Screenshot" in r.text or "Job Opening Link" in r.text

    def test_pro_create_ok_verification_pending(self, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_pro_ok_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["verification_status"] == "pending"
        assert j["posted_by_role"] == "professional"
        assert j["status"] == "open"
        # DB persistence
        db_j = mongo.jobs.find_one({"id": j["id"]}, {"_id": 0})
        assert db_j and db_j["verification_status"] == "pending"


# ---------------- GET /api/jobs & /jobs/{id} & filters ----------------
class TestJobListing:
    @pytest.fixture(scope="class")
    def seeded_jobs(self, pro_a, mongo):
        # Create one verified pro-job + one pending pro-job
        b1 = _valid_job_body(title=f"iter55_verified_{uuid.uuid4().hex[:6]}",
                             location="Hyderabad", skills_required=["React"])
        r1 = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b1, timeout=30)
        assert r1.status_code == 200
        jv = r1.json()
        # Force verified
        mongo.jobs.update_one({"id": jv["id"]},
                              {"$set": {"verification_status": "verified"}})
        b2 = _valid_job_body(title=f"iter55_pending_{uuid.uuid4().hex[:6]}",
                             location="Hyderabad", skills_required=["React"])
        r2 = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b2, timeout=30)
        assert r2.status_code == 200
        return {"verified": jv["id"], "pending": r2.json()["id"]}

    def test_student_sees_only_verified_pro_jobs(self, student_fresher, seeded_jobs):
        r = requests.get(f"{API}/jobs", headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        assert seeded_jobs["verified"] in ids
        assert seeded_jobs["pending"] not in ids

    def test_pro_sees_own_pending_and_others_verified(self, pro_a, pro_b, seeded_jobs):
        r = requests.get(f"{API}/jobs", headers=_hdr(pro_a["token"]), timeout=30)
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        # owner sees own pending
        assert seeded_jobs["pending"] in ids
        # Another pro should NOT see pro_a's pending
        r2 = requests.get(f"{API}/jobs", headers=_hdr(pro_b["token"]), timeout=30)
        ids2 = {j["id"] for j in r2.json()}
        assert seeded_jobs["pending"] not in ids2
        assert seeded_jobs["verified"] in ids2

    def test_admin_sees_all(self, admin_token, seeded_jobs):
        r = requests.get(f"{API}/jobs", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        assert seeded_jobs["verified"] in ids
        assert seeded_jobs["pending"] in ids

    def test_source_admin_filter(self, student_fresher):
        r = requests.get(f"{API}/jobs?source=admin",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        for j in r.json():
            assert j.get("source") == "admin"

    def test_skill_filter_regex(self, student_fresher, seeded_jobs):
        r = requests.get(f"{API}/jobs?skill=React",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        assert seeded_jobs["verified"] in ids

    def test_location_synonym_expansion(self, student_fresher, seeded_jobs):
        # Hyderabad seed → filter with 'hyd' should still return
        r = requests.get(f"{API}/jobs?location=Hyderabad",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        assert seeded_jobs["verified"] in ids

    def test_get_job_by_id_404(self, student_fresher):
        r = requests.get(f"{API}/jobs/nonexistent-xxx",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 404

    def test_get_job_student_has_applied_keys(self, student_fresher, seeded_jobs):
        r = requests.get(f"{API}/jobs/{seeded_jobs['verified']}",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "applied" in d
        assert "application_status" in d


# ---------------- PATCH / CLOSE / REOPEN ----------------
class TestJobMutations:
    @pytest.fixture(scope="class")
    def owned_job(self, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_mut_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        assert r.status_code == 200
        return r.json()["id"]

    def test_non_owner_pro_cannot_patch(self, pro_b, owned_job):
        r = requests.patch(f"{API}/jobs/{owned_job}",
                           headers=_hdr(pro_b["token"]),
                           json={"title": "hacked"}, timeout=30)
        assert r.status_code == 403

    def test_owner_can_patch_and_bulk_openings_synced(self, pro_a, owned_job, mongo):
        r = requests.patch(f"{API}/jobs/{owned_job}",
                           headers=_hdr(pro_a["token"]),
                           json={"open_positions": 5}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["open_positions"] == 5
        assert d["bulk_openings"] == 5

    def test_owner_close_and_reopen(self, pro_a, owned_job):
        c = requests.post(f"{API}/jobs/{owned_job}/close",
                         headers=_hdr(pro_a["token"]), timeout=30)
        assert c.status_code == 200
        g = requests.get(f"{API}/jobs/{owned_job}",
                        headers=_hdr(pro_a["token"]), timeout=30)
        assert g.json()["status"] == "closed"
        rr = requests.post(f"{API}/jobs/{owned_job}/reopen",
                          headers=_hdr(pro_a["token"]), timeout=30)
        assert rr.status_code == 200
        g2 = requests.get(f"{API}/jobs/{owned_job}",
                         headers=_hdr(pro_a["token"]), timeout=30)
        assert g2.json()["status"] == "open"

    def test_non_owner_cannot_close(self, pro_b, owned_job):
        r = requests.post(f"{API}/jobs/{owned_job}/close",
                         headers=_hdr(pro_b["token"]), timeout=30)
        assert r.status_code == 403


# ---------------- APPLICANTS ----------------
class TestApplicants:
    def test_applicants_owner_sees_student_profile_snippet(self, pro_a, student_fresher, mongo):
        b = _valid_job_body(title=f"iter55_appl_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        ap = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(student_fresher["token"]),
                           json={"job_id": jid}, timeout=30)
        assert ap.status_code == 200, ap.text
        lst = requests.get(f"{API}/jobs/{jid}/applicants",
                           headers=_hdr(pro_a["token"]), timeout=30)
        assert lst.status_code == 200
        data = lst.json()
        assert len(data) == 1
        assert "student_profile" in data[0]
        sp = data[0]["student_profile"]
        for k in ("skills", "resume_score", "current_location", "preferred_role",
                  "education", "passed_out_year"):
            assert k in sp

    def test_applicants_non_owner_403(self, pro_a, pro_b, mongo):
        b = _valid_job_body(title=f"iter55_appl2_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        r2 = requests.get(f"{API}/jobs/{jid}/applicants",
                          headers=_hdr(pro_b["token"]), timeout=30)
        assert r2.status_code == 403


# ---------------- SAVED JOBS ----------------
class TestSavedJobs:
    def test_save_unsave_and_list(self, student_fresher, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_saved_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        s1 = requests.post(f"{API}/jobs/{jid}/save",
                          headers=_hdr(student_fresher["token"]), timeout=30)
        assert s1.status_code == 200
        assert s1.json()["saved"] is True
        assert s1.json()["first_time"] is True
        # second save -> first_time false
        s2 = requests.post(f"{API}/jobs/{jid}/save",
                          headers=_hdr(student_fresher["token"]), timeout=30)
        assert s2.json()["first_time"] is False
        lst = requests.get(f"{API}/saved-jobs",
                          headers=_hdr(student_fresher["token"]), timeout=30)
        assert lst.status_code == 200
        assert any(j["id"] == jid for j in lst.json())
        d = requests.delete(f"{API}/jobs/{jid}/save",
                            headers=_hdr(student_fresher["token"]), timeout=30)
        assert d.status_code == 200
        assert d.json()["saved"] is False

    def test_saved_jobs_pro_403(self, pro_a):
        r = requests.get(f"{API}/saved-jobs", headers=_hdr(pro_a["token"]), timeout=30)
        assert r.status_code == 403


# ---------------- APPLY ----------------
class TestApply:
    def test_apply_admin_source_rejected_with_exact_copy(self, student_fresher, mongo):
        # Seed an admin walk-in job directly
        jid = f"iter55_walkin_{uuid.uuid4().hex[:8]}"
        mongo.jobs.insert_one({
            "id": jid, "title": "Walk-in", "status": "open", "source": "admin",
            "employer_id": "admin", "verification_status": "verified",
            "posted_by_role": "admin", "created_at": "2026-01-01T00:00:00Z",
        })
        r = requests.post(f"{API}/jobs/apply",
                          headers=_hdr(student_fresher["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 400
        assert "This is an Admin Walk-in & Direct Job" in r.text
        mongo.jobs.delete_one({"id": jid})

    def test_apply_credit_deduction_fresher_99(self, mongo, pro_a):
        # fresh student, fresh pro job
        stu = _signup_verified_student("iter55af", mongo)
        # give ample credits
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500, "free_uses_left": 0}})
        b = _valid_job_body(title=f"iter55_apf_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        ap = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        assert ap.status_code == 200, ap.text
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0, "credits": 1})
        assert u["credits"] == 500 - 99
        appdoc = mongo.applications.find_one({"job_id": jid, "student_id": stu["id"]}, {"_id": 0})
        assert appdoc["credits_charged"] == 99

    def test_apply_credit_deduction_experienced_99(self, mongo, pro_a):
        # Iter 67: standardized credit cost — experienced students pay the same
        # 99 credits as freshers now.
        stu = _signup_verified_student("iter55ae", mongo, mark_experienced=True)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500, "free_uses_left": 0}})
        b = _valid_job_body(title=f"iter55_ape_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        ap = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        assert ap.status_code == 200, ap.text
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0, "credits": 1})
        assert u["credits"] == 500 - 99
        appdoc = mongo.applications.find_one({"job_id": jid, "student_id": stu["id"]}, {"_id": 0})
        assert appdoc["credits_charged"] == 99

    def test_apply_dup_rejected(self, student_fresher, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_apd_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        mongo.users.update_one({"id": student_fresher["id"]}, {"$set": {"credits": 500}})
        r1 = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(student_fresher["token"]),
                           json={"job_id": jid}, timeout=30)
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(student_fresher["token"]),
                           json={"job_id": jid}, timeout=30)
        assert r2.status_code == 400
        assert "Already applied" in r2.text

    def test_job_post_reward_fires_once_at_4_apps(self, mongo, pro_a):
        # Create a job by a fresh pro so we can measure delta
        fresh_pro = _signup_verified_pro("iter55rwd", mongo)
        mongo.users.update_one({"id": fresh_pro["id"]}, {"$set": {"credits": 0}})
        b = _valid_job_body(title=f"iter55_rwd_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(fresh_pro["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        # 4 fresh students apply
        for i in range(4):
            stu = _signup_verified_student(f"iter55rwds{i}", mongo)
            mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500, "free_uses_left": 0}})
            ap = requests.post(f"{API}/jobs/apply",
                               headers=_hdr(stu["token"]),
                               json={"job_id": jid}, timeout=30)
            assert ap.status_code == 200, ap.text
        # Verify reward paid ONCE
        pro_after = mongo.users.find_one({"id": fresh_pro["id"]}, {"_id": 0})
        assert pro_after["credits"] == 200
        job_after = mongo.jobs.find_one({"id": jid}, {"_id": 0})
        assert job_after.get("posting_reward_paid") is True
        rwd_txns = list(mongo.transactions.find(
            {"user_id": fresh_pro["id"], "reason": "job_post_reward"}
        ))
        assert len(rwd_txns) == 1
        assert rwd_txns[0]["delta"] == 200


# ---------------- REFERRALS ----------------
class TestReferralsEndpoint:
    def test_referral_missing_student_or_job_400(self, pro_a):
        r = requests.post(f"{API}/referrals",
                          headers=_hdr(pro_a["token"]),
                          json={"student_id": "no-such", "job_id": "no-such"}, timeout=30)
        assert r.status_code == 400
        assert "Student or job not found" in r.text

    def test_referral_creates_row_and_increments_counter(self, pro_a, student_fresher, mongo):
        b = _valid_job_body(title=f"iter55_ref_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        # fresh student without app for this job
        stu = _signup_verified_student("iter55refstu", mongo)
        before = (mongo.users.find_one({"id": pro_a["id"]}) or {}).get("referrals_made", 0)
        rr = requests.post(f"{API}/referrals",
                           headers=_hdr(pro_a["token"]),
                           json={"student_id": stu["id"], "job_id": jid,
                                 "note": "iter55 referral"}, timeout=30)
        assert rr.status_code == 200, rr.text
        app_id = rr.json()["application_id"]
        row = mongo.applications.find_one({"id": app_id}, {"_id": 0})
        assert row["referrer_pro_id"] == pro_a["id"]
        assert row["status"] == "referred"
        # dup
        dup = requests.post(f"{API}/referrals",
                            headers=_hdr(pro_a["token"]),
                            json={"student_id": stu["id"], "job_id": jid}, timeout=30)
        assert dup.status_code == 400
        after = (mongo.users.find_one({"id": pro_a["id"]}) or {}).get("referrals_made", 0)
        assert after == before + 1


# ---------------- APPLICATIONS (list, pool, timeline) ----------------
class TestApplications:
    def test_student_list_hydrated_with_company_location(self, mongo, pro_a):
        stu = _signup_verified_student("iter55appl", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_al_{uuid.uuid4().hex[:6]}",
                            location="Pune", company="AcmeCorp")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        ap = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        assert ap.status_code == 200
        lst = requests.get(f"{API}/applications",
                           headers=_hdr(stu["token"]), timeout=30)
        assert lst.status_code == 200
        mine = [a for a in lst.json() if a["job_id"] == jid]
        assert mine and mine[0].get("company") == "AcmeCorp"
        assert mine[0].get("location") == "Pune"

    def test_applications_pool_pro_only(self, student_fresher, pro_a):
        r = requests.get(f"{API}/applications/pool",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 403
        r2 = requests.get(f"{API}/applications/pool",
                          headers=_hdr(pro_a["token"]), timeout=30)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)
        # verify shape
        if r2.json():
            first = r2.json()[0]
            assert "student_profile" in first
            for k in ("education", "resume_score", "resume_link"):
                assert k in first["student_profile"]

    def test_timeline_returns_history_and_pending(self, mongo, pro_a):
        stu = _signup_verified_student("iter55tl", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_tl_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        ap = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        tl = requests.get(f"{API}/applications/{appid}/timeline",
                          headers=_hdr(stu["token"]), timeout=30)
        assert tl.status_code == 200
        d = tl.json()
        assert d["current_status"] == "applied"
        assert isinstance(d["history"], list)
        assert isinstance(d["pending_changes"], list)


# ---------------- STATUS-CHANGE / HIRE / REFER-OWN ----------------
class TestStatusPipeline:
    def test_status_request_non_participant_403(self, mongo, pro_a, pro_b):
        stu = _signup_verified_student("iter55stg", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_stg_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        # unrelated pro tries to move status
        r2 = requests.post(f"{API}/applications/status",
                           headers=_hdr(pro_b["token"]),
                           json={"application_id": appid, "new_status": "shortlisted"}, timeout=30)
        assert r2.status_code == 403

    def test_status_request_student_own_creates_pending(self, mongo, pro_a):
        stu = _signup_verified_student("iter55sto", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_sto_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        r2 = requests.post(f"{API}/applications/status",
                           headers=_hdr(stu["token"]),
                           json={"application_id": appid, "new_status": "shortlisted",
                                 "note": "iter55"}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "pending"
        pending = mongo.status_changes.find_one({"application_id": appid, "status": "pending"})
        assert pending is not None

    def test_hire_missing_proof_and_note_400(self, mongo, pro_a):
        stu = _signup_verified_student("iter55hire", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_hr_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        r2 = requests.post(f"{API}/applications/hire",
                          headers=_hdr(pro_a["token"]),
                          json={"application_id": appid}, timeout=30)
        assert r2.status_code == 400
        assert "supporting evidence" in r2.text.lower() or "note" in r2.text.lower()

    def test_hire_non_poster_403(self, mongo, pro_a, pro_b):
        stu = _signup_verified_student("iter55hr2", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_hr2_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        r2 = requests.post(f"{API}/applications/hire",
                          headers=_hdr(pro_b["token"]),
                          json={"application_id": appid, "note": "trying"}, timeout=30)
        assert r2.status_code == 403

    def test_hire_ok_flips_to_hired_pending(self, mongo, pro_a):
        stu = _signup_verified_student("iter55hok", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_hok_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        r2 = requests.post(f"{API}/applications/hire",
                          headers=_hdr(pro_a["token"]),
                          json={"application_id": appid, "note": "hired via iter55"}, timeout=30)
        assert r2.status_code == 200, r2.text
        appdoc = mongo.applications.find_one({"id": appid}, {"_id": 0})
        assert appdoc["status"] == "hired_pending"
        sc = mongo.status_changes.find_one({"application_id": appid, "to_status": "hired"})
        assert sc is not None

    def test_refer_own_walks_to_referred(self, mongo, pro_a):
        stu = _signup_verified_student("iter55ro", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_ro_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        pro_before = mongo.users.find_one({"id": pro_a["id"]}).get("referrals_made", 0)
        r2 = requests.post(f"{API}/applications/refer-own",
                          headers=_hdr(pro_a["token"]),
                          json={"application_id": appid, "note": "iter55"}, timeout=30)
        assert r2.status_code == 200, r2.text
        appdoc = mongo.applications.find_one({"id": appid}, {"_id": 0})
        assert appdoc["status"] == "referred"
        assert appdoc["referrer_pro_id"] == pro_a["id"]
        sc = mongo.status_changes.find_one({"application_id": appid, "to_status": "referred",
                                            "status": "approved"})
        assert sc is not None
        pro_after = mongo.users.find_one({"id": pro_a["id"]}).get("referrals_made", 0)
        assert pro_after == pro_before + 1

    def test_refer_own_non_poster_403(self, mongo, pro_a, pro_b):
        stu = _signup_verified_student("iter55rox", mongo)
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        b = _valid_job_body(title=f"iter55_rox_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
        requests.post(f"{API}/jobs/apply",
                      headers=_hdr(stu["token"]),
                      json={"job_id": jid}, timeout=30)
        appid = mongo.applications.find_one({"student_id": stu["id"], "job_id": jid})["id"]
        r2 = requests.post(f"{API}/applications/refer-own",
                          headers=_hdr(pro_b["token"]),
                          json={"application_id": appid}, timeout=30)
        assert r2.status_code == 403


# ---------------- RESUBMIT ----------------
class TestResubmit:
    def test_resubmit_only_rejected_400(self, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_rs1_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        # still pending
        r2 = requests.post(f"{API}/jobs/{jid}/resubmit",
                          headers=_hdr(pro_a["token"]), timeout=30)
        assert r2.status_code == 400
        assert "rejected" in r2.text.lower()

    def test_resubmit_non_owner_403(self, pro_a, pro_b, mongo):
        b = _valid_job_body(title=f"iter55_rs2_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "rejected"}})
        r2 = requests.post(f"{API}/jobs/{jid}/resubmit",
                          headers=_hdr(pro_b["token"]), timeout=30)
        assert r2.status_code == 403

    def test_resubmit_ok_flips_to_pending(self, pro_a, mongo):
        b = _valid_job_body(title=f"iter55_rs3_{uuid.uuid4().hex[:6]}")
        r = requests.post(f"{API}/jobs", headers=_hdr(pro_a["token"]), json=b, timeout=30)
        jid = r.json()["id"]
        mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "rejected"}})
        r2 = requests.post(f"{API}/jobs/{jid}/resubmit",
                          headers=_hdr(pro_a["token"]), timeout=30)
        assert r2.status_code == 200
        assert r2.json()["verification_status"] == "pending"
        db_j = mongo.jobs.find_one({"id": jid}, {"_id": 0})
        assert db_j["verification_status"] == "pending"


# ---------------- PROFESSIONALS ----------------
class TestProfessionals:
    def test_professionals_endpoint_ok(self, student_fresher):
        r = requests.get(f"{API}/professionals",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- ADJACENT (helpers still coupled) ----------------
class TestAdjacent:
    def test_wallet_ok(self, student_fresher):
        r = requests.get(f"{API}/wallet",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200

    def test_wallet_deposit_order_ok(self, student_fresher):
        r = requests.post(f"{API}/wallet/deposit/create-order",
                          headers=_hdr(student_fresher["token"]),
                          json={"amount_inr": 200}, timeout=30)  # Iter 64: min first deposit is ₹200
        assert r.status_code == 200

    def test_auth_me_ok(self, student_fresher):
        r = requests.get(f"{API}/auth/me",
                         headers=_hdr(student_fresher["token"]), timeout=30)
        assert r.status_code == 200

    def test_admin_transactions_search_ok(self, admin_token):
        r = requests.get(f"{API}/admin/transactions/search",
                         headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200

    def test_interviews_book_reachable(self, student_fresher):
        r = requests.post(f"{API}/interviews/book",
                          headers=_hdr(student_fresher["token"]),
                          json={"slot_id": "nonexistent_xxx"}, timeout=30)
        assert r.status_code < 500
