"""Iteration-6 backend contract tests.

Covers:
- /api/interviews/{slot_id}/joined validations (403 for non-participant; success for participants)
- /api/interviews/{slot_id}/complete now requires rating body + both-joined + >=15min from start
- Pro leaderboard rows include `rating` + `ratings_count`
- Pro-posted job: +100 ONE-TIME reward when 4 unique non-withdrawn applications received
  (uses job.posting_reward_paid flag); employer-posted jobs do NOT receive this bonus
- /api/applications/hire requires note OR proof; creates status_changes pending
- Admin /api/admin/status-changes/action approve: +1500 to employer, +500 to referrer pro (if any)
- /api/applications/refer-own: only posting pro; status → referred; referrer_pro_id set
- GET /api/jobs filters: pros see own + employer jobs, NOT other pros' jobs;
  ?mine=true returns only own with applications_count

Uses pymongo (sync) ONLY to backdate slots / set joined_by where the production
HTTP flow has time-window constraints.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import API, auth_headers, _signup_verify

load_dotenv()


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------- Interview joined + complete validation ----------
class TestInterviewJoinedAndComplete:
    def test_joined_endpoint(self, session, professional, student):
        start = _iso(datetime.now(timezone.utc) + timedelta(days=2))
        end = _iso(datetime.now(timezone.utc) + timedelta(days=2, hours=1))
        r = session.post(f"{API}/interviews/slots", json={"start_at": start, "end_at": end}, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        slot_id = r.json()["id"]
        # Student books
        rb = session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        assert rb.status_code == 200, rb.text
        # Non-participant attempts joined -> 403
        outsider = _signup_verify(session, "student", prefix="OUTSIDER")
        rj = session.post(f"{API}/interviews/{slot_id}/joined", json={}, headers=auth_headers(outsider["token"]))
        assert rj.status_code == 403, rj.text
        # Participants succeed (idempotent)
        for tok in (professional["token"], student["token"]):
            r2 = session.post(f"{API}/interviews/{slot_id}/joined", json={}, headers=auth_headers(tok))
            assert r2.status_code == 200, r2.text
        # DB reflects joined_by contains both participants
        slot_doc = _mongo().interview_slots.find_one({"id": slot_id})
        assert professional["user"]["id"] in (slot_doc.get("joined_by") or [])
        assert student["user"]["id"] in (slot_doc.get("joined_by") or [])

    def test_complete_requires_both_joined(self, session, professional, student):
        start = _iso(datetime.now(timezone.utc) + timedelta(days=2))
        end = _iso(datetime.now(timezone.utc) + timedelta(days=2, hours=1))
        r = session.post(f"{API}/interviews/slots", json={"start_at": start, "end_at": end}, headers=auth_headers(professional["token"]))
        slot_id = r.json()["id"]
        session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        # Backdate but DO NOT mark both joined
        coll = _mongo().interview_slots
        past = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        e2 = (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat()
        coll.update_one({"id": slot_id}, {"$set": {"start_at": past, "end_at": e2, "joined_by": [professional["user"]["id"]]}})
        r2 = session.post(f"{API}/interviews/{slot_id}/complete", json={"rating": 7}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 400, r2.text
        assert "join" in r2.json().get("detail", "").lower()

    def test_complete_requires_min_duration(self, session, professional, student):
        start = _iso(datetime.now(timezone.utc) + timedelta(days=2))
        end = _iso(datetime.now(timezone.utc) + timedelta(days=2, hours=1))
        r = session.post(f"{API}/interviews/slots", json={"start_at": start, "end_at": end}, headers=auth_headers(professional["token"]))
        slot_id = r.json()["id"]
        session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        coll = _mongo().interview_slots
        # Start only 5 min ago — fails 15-min rule
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        e2 = (datetime.now(timezone.utc) + timedelta(minutes=55)).isoformat()
        coll.update_one({"id": slot_id}, {"$set": {"start_at": past, "end_at": e2, "joined_by": [professional["user"]["id"], student["user"]["id"]]}})
        r2 = session.post(f"{API}/interviews/{slot_id}/complete", json={"rating": 7}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 400, r2.text
        assert "15" in r2.json().get("detail", "") or "minutes" in r2.json().get("detail", "").lower()

    def test_complete_happy_returns_35_and_pro_rating(self, session, professional, student):
        start = _iso(datetime.now(timezone.utc) + timedelta(days=2))
        end = _iso(datetime.now(timezone.utc) + timedelta(days=2, hours=1))
        r = session.post(f"{API}/interviews/slots", json={"start_at": start, "end_at": end}, headers=auth_headers(professional["token"]))
        slot_id = r.json()["id"]
        session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        coll = _mongo().interview_slots
        past = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        e2 = (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat()
        coll.update_one({"id": slot_id}, {"$set": {"start_at": past, "end_at": e2, "joined_by": [professional["user"]["id"], student["user"]["id"]]}})
        r2 = session.post(f"{API}/interviews/{slot_id}/complete", json={"rating": 9, "feedback": "great"}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["earned"] == 35
        assert body["pro_rating"] == 9.0
        assert body["candidate_rating"] == 9


# ---------- Pro leaderboard exposes rating + ratings_count ----------
class TestProLeaderboardRating:
    def test_leaderboard_row_shape(self, session, professional):
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0, "expected at least 1 pro on leaderboard"
        # Schema check: any returned row must include rating + ratings_count
        for k in ("rating", "ratings_count", "rank", "id", "name"):
            assert k in rows[0], f"missing {k} in pro leaderboard row"
        assert isinstance(rows[0]["rating"], (int, float))
        assert isinstance(rows[0]["ratings_count"], int)


# ---------- Job posting reward (one-time, pro only) ----------
def _pro_post_job(session, pro_token, title="Iter6 Pro Job"):
    body = {"title": title, "company": "ProCo", "description": "Pro-posted role", "location": "Remote", "skills_required": ["python"], "category": "fresher"}
    r = session.post(f"{API}/jobs", json=body, headers=auth_headers(pro_token))
    assert r.status_code == 200, r.text
    return r.json()


def _employer_post_job(session, emp_token, title="Iter6 Emp Job"):
    body = {"title": title, "company": "EmpCo", "description": "Employer-posted role", "location": "Remote", "skills_required": ["python"], "category": "fresher"}
    r = session.post(f"{API}/jobs", json=body, headers=auth_headers(emp_token))
    assert r.status_code == 200, r.text
    return r.json()


class TestJobPostReward:
    def test_pro_posted_job_4_apps_awards_100_once(self, session, professional):
        # baseline pro credits
        w0 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        job = _pro_post_job(session, professional["token"])
        job_id = job["id"]
        # Apply 4 unique students (each uses a free use)
        student_tokens = []
        for i in range(4):
            s = _signup_verify(session, "student", prefix=f"APP{i}")
            student_tokens.append(s["token"])
            r = session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(s["token"]))
            assert r.status_code == 200, r.text
        # After 4th apply, pro should have w0 + 100
        w1 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        assert w1 == w0 + 100, f"Expected one-time +100, got {w1 - w0}"
        # 5th apply must NOT pay again
        s5 = _signup_verify(session, "student", prefix="APP5")
        r5 = session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(s5["token"]))
        assert r5.status_code == 200, r5.text
        w2 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        assert w2 == w1, "Reward must be one-time"
        # Job has posting_reward_paid flag set
        job_doc = _mongo().jobs.find_one({"id": job_id})
        assert job_doc.get("posting_reward_paid") is True

    def test_employer_posted_job_no_reward(self, session, employer):
        # Employer credits baseline
        w0 = session.get(f"{API}/wallet", headers=auth_headers(employer["token"])).json()["credits"]
        job = _employer_post_job(session, employer["token"])
        job_id = job["id"]
        for i in range(4):
            s = _signup_verify(session, "student", prefix=f"EMPA{i}")
            r = session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(s["token"]))
            assert r.status_code == 200, r.text
        w1 = session.get(f"{API}/wallet", headers=auth_headers(employer["token"])).json()["credits"]
        assert w1 == w0, "Employer-posted jobs do not get the +100 reward"
        job_doc = _mongo().jobs.find_one({"id": job_id})
        assert not job_doc.get("posting_reward_paid")


# ---------- /api/applications/hire requires note or proof ----------
class TestHireValidation:
    def test_hire_no_note_no_proof_400(self, session, employer):
        job = _employer_post_job(session, employer["token"], title="HireValJob")
        s = _signup_verify(session, "student", prefix="HIREVAL")
        r = session.post(f"{API}/jobs/apply", json={"job_id": job["id"]}, headers=auth_headers(s["token"]))
        assert r.status_code == 200, r.text
        app = _mongo().applications.find_one({"job_id": job["id"], "student_id": s["user"]["id"]})
        r2 = session.post(f"{API}/applications/hire", json={"application_id": app["id"]}, headers=auth_headers(employer["token"]))
        assert r2.status_code == 400, r2.text

    def test_hire_with_note_goes_pending(self, session, employer):
        job = _employer_post_job(session, employer["token"], title="HirePendJob")
        s = _signup_verify(session, "student", prefix="HIREPEND")
        session.post(f"{API}/jobs/apply", json={"job_id": job["id"]}, headers=auth_headers(s["token"]))
        app = _mongo().applications.find_one({"job_id": job["id"], "student_id": s["user"]["id"]})
        r = session.post(f"{API}/applications/hire", json={"application_id": app["id"], "note": "Offered SDE1"}, headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        assert "change_id" in r.json()
        app2 = _mongo().applications.find_one({"id": app["id"]})
        assert app2["status"] == "hired_pending"
        sc = _mongo().status_changes.find_one({"id": r.json()["change_id"]})
        assert sc and sc["status"] == "pending"


# ---------- Admin approve hire: +1500 employer, +500 referrer ----------
class TestAdminApproveHire:
    def test_employer_gets_1500_and_referrer_500(self, session, employer, professional, admin_token):
        # Employer-posted job; pro refers student via /referrals (creates an application with referrer_pro_id)
        job = _employer_post_job(session, employer["token"], title="HireAdminJob")
        s = _signup_verify(session, "student", prefix="HIREAPV")
        r = session.post(
            f"{API}/referrals",
            json={"student_id": s["user"]["id"], "job_id": job["id"], "note": "fit"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        app_id = r.json()["application_id"]
        # Baseline credits
        emp0 = session.get(f"{API}/wallet", headers=auth_headers(employer["token"])).json()["credits"]
        pro0 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        # Employer submits hire pending
        rh = session.post(f"{API}/applications/hire", json={"application_id": app_id, "note": "Onboarded"}, headers=auth_headers(employer["token"]))
        assert rh.status_code == 200, rh.text
        change_id = rh.json()["change_id"]
        # Admin approves
        ra = session.post(f"{API}/admin/status-changes/action", json={"change_id": change_id, "action": "approve"}, headers=auth_headers(admin_token))
        assert ra.status_code == 200, ra.text
        # Wallets
        emp1 = session.get(f"{API}/wallet", headers=auth_headers(employer["token"])).json()["credits"]
        pro1 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        assert emp1 - emp0 == 1500, f"employer delta={emp1 - emp0}"
        assert pro1 - pro0 == 500, f"pro delta={pro1 - pro0}"
        app2 = _mongo().applications.find_one({"id": app_id})
        assert app2["status"] == "hired"


# ---------- /api/applications/refer-own ----------
class TestReferOwn:
    def test_only_posting_pro_can_refer_own(self, session, professional):
        # Pro posts a job
        job = _pro_post_job(session, professional["token"], title="ReferOwnJob")
        s = _signup_verify(session, "student", prefix="ROWN")
        r = session.post(f"{API}/jobs/apply", json={"job_id": job["id"]}, headers=auth_headers(s["token"]))
        assert r.status_code == 200, r.text
        app = _mongo().applications.find_one({"job_id": job["id"], "student_id": s["user"]["id"]})
        # Another pro cannot refer
        pro2 = _signup_verify(session, "professional", prefix="OTHERPRO")
        r_other = session.post(f"{API}/applications/refer-own", json={"application_id": app["id"]}, headers=auth_headers(pro2["token"]))
        assert r_other.status_code == 403, r_other.text
        # Posting pro can
        r_own = session.post(f"{API}/applications/refer-own", json={"application_id": app["id"], "note": "Strong fit"}, headers=auth_headers(professional["token"]))
        assert r_own.status_code == 200, r_own.text
        app2 = _mongo().applications.find_one({"id": app["id"]})
        assert app2["status"] == "referred"
        assert app2.get("referrer_pro_id") == professional["user"]["id"]
        # History contains shortlisted -> referred entries
        hist_statuses = [h["status"] for h in (app2.get("status_history") or [])]
        assert "shortlisted" in hist_statuses and "referred" in hist_statuses


# ---------- GET /api/jobs visibility filters ----------
class TestJobsVisibilityForPro:
    def test_pro_does_not_see_other_pro_jobs_but_sees_employer_jobs(self, session, professional, employer):
        pro2 = _signup_verify(session, "professional", prefix="HIDEPRO")
        job_a = _pro_post_job(session, pro2["token"], title="VisOtherProJob")
        job_b = _employer_post_job(session, employer["token"], title="VisEmpJob")
        job_c = _pro_post_job(session, professional["token"], title="VisOwnProJob")
        r = session.get(f"{API}/jobs", headers=auth_headers(professional["token"]))
        assert r.status_code == 200
        ids = {j["id"] for j in r.json()}
        assert job_c["id"] in ids, "should see own pro-posted job"
        assert job_b["id"] in ids, "should see open employer-posted job"
        assert job_a["id"] not in ids, "should NOT see other pro's posted job"

    def test_mine_true_returns_only_caller_jobs_with_applications_count(self, session, professional, employer):
        # post a job + 2 apps so applications_count > 0
        job = _pro_post_job(session, professional["token"], title="MineTrueJob")
        for i in range(2):
            s = _signup_verify(session, "student", prefix=f"MT{i}")
            session.post(f"{API}/jobs/apply", json={"job_id": job["id"]}, headers=auth_headers(s["token"]))
        # employer post (must NOT appear in pro's mine list)
        job_e = _employer_post_job(session, employer["token"], title="MineTrueNotMineJob")
        r = session.get(f"{API}/jobs?mine=true", headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        rows = r.json()
        ids = {j["id"] for j in rows}
        assert job["id"] in ids
        assert job_e["id"] not in ids
        target = next(j for j in rows if j["id"] == job["id"])
        assert target.get("applications_count", 0) >= 2
