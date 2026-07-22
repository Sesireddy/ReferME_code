"""Iter 75 — Job Application credit-deduction, rollback & wallet-label contract.

Backend-only. Every test creates its own disposable student/pro so runs are hermetic.

Rules under test (see /app/memory + review_request for the full spec):
1. Insert-first, deduct-later: /api/jobs/apply must insert `applications` row with
   `credits_charged: 0`, then deduct 99 credits via `_credit_user` with
   `meta.label == "Job Application – <title> at <company>"`, then update
   `credits_charged = 99`. Rollback on any deduction failure.
2. Rejection messages unchanged for insufficient credits, already-applied,
   closed jobs, admin walk-in, incomplete profile.
3. Free-pass path (`free_uses_left > 0`) skips wallet completely.
4. +200 job-post reward at 4th valid application still fires exactly once.
"""
import os
import uuid
import pytest
import requests
from datetime import date, timedelta
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


def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ["MONGO_URL"])
    yield mc[os.environ["DB_NAME"]]
    mc.close()


def _signup_verify(role: str, prefix: str, domain: str):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    body = {"email": email, "password": pw, "role": role, "name": f"{prefix} u"}
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    v = requests.post(f"{API}/auth/verify-otp",
                      json={"email": email, "otp": otp, "purpose": "verify_email"}, timeout=30)
    assert v.status_code == 200, v.text
    return {"email": email, "pw": pw, "token": v.json()["token"], "id": v.json()["user"]["id"]}


def _make_complete_student(mongo, prefix: str = "iter75stu"):
    """Signup + email verify + patch profile to satisfy `student_missing_fields`."""
    s = _signup_verify("student", prefix, "referme.io")
    mongo.users.update_one(
        {"id": s["id"]},
        {"$set": {
            "name": "Iter75 Student",
            "is_email_verified": True,
            "profile.preferred_role": "fresher",
            "profile.phone": "9876543210",
            "profile.phone_verified": True,
            "profile.gender": "male",
            "profile.dob": "2000-01-01",
            "profile.education": "BE",
            "profile.passed_out_year": 2022,
            "profile.current_location": "Bangalore",
            "profile.skills": ["Python", "FastAPI"],
            "profile.resume_link": "https://example.com/resume.pdf",
            "profile_complete": True,
            "credits": 500,
            "free_uses_left": 0,
        }},
    )
    return s


def _make_pro(mongo, prefix: str = "iter75pro"):
    p = _signup_verify("professional", prefix, "acmecorp.io")
    mongo.users.update_one(
        {"id": p["id"]},
        {"$set": {
            "profile.phone": "9876543210",
            "profile.phone_verified": True,
            "profile.company": "AcmeCorp",
        }},
    )
    return p


def _post_verified_job(pro, mongo, title_suffix: str = "", company: str = "AcmeCorp",
                      last_date_delta_days: int = 30):
    body = {
        "title": f"Iter75 Backend Engineer {title_suffix or uuid.uuid4().hex[:6]}",
        "description": "Build APIs.",
        "location": "Bangalore",
        "skills_required": ["Python"],
        "company": company,
        "salary_range": "10-15 LPA",
        "industry_type": "IT Services",
        "experience_required": 2,
        "open_positions_label": "1",
        "category": "experienced",
        "proof_link": "https://example.com/job",
        "last_date_to_apply": (date.today() + timedelta(days=last_date_delta_days)).isoformat(),
    }
    r = requests.post(f"{API}/jobs", headers=_hdr(pro["token"]), json=body, timeout=30)
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    mongo.jobs.update_one({"id": jid}, {"$set": {"verification_status": "verified"}})
    return jid, body["title"], company


# ---------- Test 1: Happy path ----------
class TestHappyPath:
    def test_happy_path_deducts_99_after_insert(self, mongo):
        pro = _make_pro(mongo, "iter75happy_pro")
        stu = _make_complete_student(mongo, "iter75happy_stu")
        jid, title, company = _post_verified_job(pro, mongo, "happy")
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("used_free") is False
        # applications row
        appdoc = mongo.applications.find_one({"job_id": jid, "student_id": stu["id"]},
                                             {"_id": 0})
        assert appdoc, "applications row missing"
        assert appdoc["credits_charged"] == 99
        assert appdoc["status"] == "applied"
        # transactions row
        txns = list(mongo.transactions.find(
            {"user_id": stu["id"], "reason": "job_application"}
        ))
        assert len(txns) == 1
        t = txns[0]
        assert t["delta"] == -99
        label = (t.get("meta") or {}).get("label") or ""
        assert label.startswith("Job Application – "), f"label was: {label!r}"
        assert title in label, f"title {title!r} missing from label {label!r}"
        assert company in label, f"company {company!r} missing from label {label!r}"
        # wallet
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0, "credits": 1})
        assert u["credits"] == 500 - 99 == 401


# ---------- Test 2: Insufficient credits ----------
class TestInsufficientCredits:
    def test_402_no_side_effects(self, mongo):
        pro = _make_pro(mongo, "iter75ins_pro")
        stu = _make_complete_student(mongo, "iter75ins_stu")
        mongo.users.update_one({"id": stu["id"]},
                               {"$set": {"credits": 50, "free_uses_left": 0}})
        jid, _, _ = _post_verified_job(pro, mongo, "ins")
        # snapshot before
        txns_before = mongo.transactions.count_documents({"user_id": stu["id"]})
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 402, r.text
        detail = r.json().get("detail", "")
        assert "Insufficient credits" in detail
        # No applications row
        assert mongo.applications.count_documents(
            {"job_id": jid, "student_id": stu["id"]}
        ) == 0
        # No transactions inserted
        txns_after = mongo.transactions.count_documents({"user_id": stu["id"]})
        assert txns_after == txns_before
        # wallet unchanged
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0, "credits": 1})
        assert u["credits"] == 50
        # cache detail string for report
        pytest._iter75_detail_insufficient = detail


# ---------- Test 3: Already applied ----------
class TestAlreadyApplied:
    def test_duplicate_apply_returns_400(self, mongo):
        pro = _make_pro(mongo, "iter75dup_pro")
        stu = _make_complete_student(mongo, "iter75dup_stu")
        jid, _, _ = _post_verified_job(pro, mongo, "dup")
        r1 = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        assert r1.status_code == 200, r1.text
        credits_after_first = mongo.users.find_one({"id": stu["id"]})["credits"]
        r2 = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                           json={"job_id": jid}, timeout=30)
        assert r2.status_code == 400
        detail = r2.json().get("detail", "")
        assert detail == "Already applied", f"got: {detail!r}"
        # exactly one applications row
        assert mongo.applications.count_documents(
            {"job_id": jid, "student_id": stu["id"]}
        ) == 1
        # exactly one job_application transaction
        assert mongo.transactions.count_documents(
            {"user_id": stu["id"], "reason": "job_application", "meta.job_id": jid}
        ) == 1
        # wallet not double-charged
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0, "credits": 1})
        assert u["credits"] == credits_after_first
        pytest._iter75_detail_already_applied = detail


# ---------- Test 4: Closed job (past last_date_to_apply) ----------
class TestClosedJob:
    def test_past_last_date_400(self, mongo):
        pro = _make_pro(mongo, "iter75cls_pro")
        stu = _make_complete_student(mongo, "iter75cls_stu")
        jid, _, _ = _post_verified_job(pro, mongo, "cls")
        # backdate the last_date_to_apply
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        mongo.jobs.update_one({"id": jid}, {"$set": {"last_date_to_apply": yesterday}})
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Applications Closed" in detail, f"got: {detail!r}"
        # no side effects
        assert mongo.applications.count_documents(
            {"job_id": jid, "student_id": stu["id"]}
        ) == 0
        assert mongo.transactions.count_documents(
            {"user_id": stu["id"], "reason": "job_application"}
        ) == 0
        pytest._iter75_detail_closed = detail


# ---------- Test 5: Admin walk-in ----------
class TestAdminWalkIn:
    def test_admin_source_400(self, mongo):
        stu = _make_complete_student(mongo, "iter75wi_stu")
        jid = f"iter75_walkin_{uuid.uuid4().hex[:8]}"
        mongo.jobs.insert_one({
            "id": jid, "title": "Walk-in", "status": "open", "source": "admin",
            "employer_id": "admin", "verification_status": "verified",
            "posted_by_role": "admin",
            "last_date_to_apply": (date.today() + timedelta(days=10)).isoformat(),
            "created_at": "2026-01-01T00:00:00Z",
        })
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Admin Walk-in" in detail, f"got: {detail!r}"
        # no side effects
        assert mongo.applications.count_documents(
            {"job_id": jid, "student_id": stu["id"]}
        ) == 0
        assert mongo.transactions.count_documents(
            {"user_id": stu["id"], "reason": "job_application"}
        ) == 0
        mongo.jobs.delete_one({"id": jid})
        pytest._iter75_detail_admin = detail


# ---------- Test 6: Incomplete profile ----------
class TestIncompleteProfile:
    def test_incomplete_profile_400_structured(self, mongo):
        # Signup + verify email only — DO NOT patch profile completeness fields.
        stu = _signup_verify("student", "iter75inc", "referme.io")
        # ensure credits are enough so we can prove the profile-gate is the reason
        mongo.users.update_one({"id": stu["id"]}, {"$set": {"credits": 500}})
        pro = _make_pro(mongo, "iter75inc_pro")
        jid, _, _ = _post_verified_job(pro, mongo, "inc")
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail")
        # detail must be the structured dict
        assert isinstance(detail, dict), f"expected dict, got: {type(detail).__name__}"
        assert detail.get("code") == "PROFILE_INCOMPLETE"
        assert isinstance(detail.get("missing_fields"), list)
        assert len(detail["missing_fields"]) > 0
        # no side effects
        assert mongo.applications.count_documents(
            {"job_id": jid, "student_id": stu["id"]}
        ) == 0
        assert mongo.transactions.count_documents(
            {"user_id": stu["id"], "reason": "job_application"}
        ) == 0
        pytest._iter75_detail_profile = detail


# ---------- Test 7: Free-pass path ----------
class TestFreePass:
    def test_free_use_no_wallet_touch(self, mongo):
        pro = _make_pro(mongo, "iter75fp_pro")
        stu = _make_complete_student(mongo, "iter75fp_stu")
        mongo.users.update_one({"id": stu["id"]},
                               {"$set": {"credits": 0, "free_uses_left": 1}})
        jid, _, _ = _post_verified_job(pro, mongo, "fp")
        txns_before = mongo.transactions.count_documents({"user_id": stu["id"]})
        r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                          json={"job_id": jid}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("used_free") is True
        # applications: credits_charged == 0
        appdoc = mongo.applications.find_one({"job_id": jid, "student_id": stu["id"]},
                                             {"_id": 0})
        assert appdoc["credits_charged"] == 0
        # no new transactions
        assert mongo.transactions.count_documents({"user_id": stu["id"]}) == txns_before
        # wallet + free counter
        u = mongo.users.find_one({"id": stu["id"]}, {"_id": 0})
        assert u["credits"] == 0
        assert u["free_uses_left"] == 0


# ---------- Test 8: +200 job-post reward regression ----------
class TestJobPostRewardRegression:
    def test_four_apps_pro_gets_200_once(self, mongo):
        pro = _make_pro(mongo, "iter75rwd_pro")
        # Ensure known starting credits
        mongo.users.update_one({"id": pro["id"]}, {"$set": {"credits": 0}})
        jid, _, _ = _post_verified_job(pro, mongo, "rwd")
        for i in range(4):
            stu = _make_complete_student(mongo, f"iter75rwd_s{i}")
            r = requests.post(f"{API}/jobs/apply", headers=_hdr(stu["token"]),
                              json={"job_id": jid}, timeout=30)
            assert r.status_code == 200, r.text
        # pro wallet == 200 (from the single reward)
        pro_doc = mongo.users.find_one({"id": pro["id"]}, {"_id": 0, "credits": 1})
        assert pro_doc["credits"] == 200
        # job flagged as reward-paid
        job = mongo.jobs.find_one({"id": jid}, {"_id": 0})
        assert job.get("posting_reward_paid") is True
        # exactly one job_post_reward transaction
        rwd_txns = list(mongo.transactions.find(
            {"user_id": pro["id"], "reason": "job_post_reward"}
        ))
        assert len(rwd_txns) == 1
        assert rwd_txns[0]["delta"] == 200
