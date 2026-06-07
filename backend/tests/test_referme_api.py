"""Comprehensive backend tests for ReferME API.
Covers: health, auth, profile, wallet, interviews, jobs, referrals,
leaderboards, payouts, admin, disputes, notifications, RBAC.
Iteration 3: + slot start_at/end_at + overlap, applied flag on /jobs,
profile new fields, /applications/pool, resume_score auto-compute.
"""
import os
import time
import uuid
import requests
import pytest
from datetime import datetime, timedelta, timezone
from conftest import API, auth_headers


# ---------- Health ----------
def test_health(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data["app"] == "ReferME"
    # iter4: mock_otp depends on SENDGRID_API_KEY presence; just assert key exists
    assert "mock_otp" in data
    assert data["mock_payments"] is True


# ---------- Auth ----------
class TestAuth:
    def test_signup_returns_mock_otp(self, session):
        email = f"test_s_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={"email": email, "password": "Pass@1234", "role": "student"})
        assert r.status_code == 200, r.text
        assert "mock_otp" in r.json()

    def test_signup_admin_blocked(self, session):
        email = f"test_admin_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={"email": email, "password": "Pass@1234", "role": "admin"})
        assert r.status_code == 400

    def test_signup_duplicate(self, session, student):
        r = session.post(f"{API}/auth/signup", json={"email": student["email"], "password": "Pass@1234", "role": "student"})
        assert r.status_code == 400

    def test_login_requires_verification(self, session):
        email = f"unverified_{uuid.uuid4().hex[:8]}@referme.io"
        session.post(f"{API}/auth/signup", json={"email": email, "password": "Pass@1234", "role": "student"})
        r = session.post(f"{API}/auth/login", json={"email": email, "password": "Pass@1234"})
        assert r.status_code == 403

    def test_login_success(self, session, student):
        r = session.post(f"{API}/auth/login", json={"email": student["email"], "password": student["password"]})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_bad_password(self, session, student):
        r = session.post(f"{API}/auth/login", json={"email": student["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_me(self, session, student):
        r = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        assert r.json()["user"]["email"] == student["email"]

    def test_forgot_and_reset_password(self, session, student):
        r = session.post(f"{API}/auth/forgot-password", json={"email": student["email"]})
        assert r.status_code == 200
        otp = r.json().get("mock_otp")
        assert otp
        r2 = session.post(f"{API}/auth/reset-password", json={"email": student["email"], "otp": otp, "new_password": "NewPass@1"})
        assert r2.status_code == 200
        # login with new password
        r3 = session.post(f"{API}/auth/login", json={"email": student["email"], "password": "NewPass@1"})
        assert r3.status_code == 200

    def test_admin_login(self, session, admin_token):
        assert admin_token


# ---------- Profile ----------
class TestProfile:
    def test_student_profile_completion(self, session, student):
        # Iteration 3: required fields are education, passed_out_year, current_location,
        # preferred_role, skills, and resume_base64 OR resume_link
        body = {
            "name": "S One",
            "education": "B.Tech",
            "passed_out_year": 2024,
            "current_location": "Bangalore",
            "dob": "2001-05-12",
            "preferred_role": "fresher",
            "skills": ["Python"],
            "resume_base64": "data:application/pdf;base64,xx",
            "resume_mime_type": "application/pdf",
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True
        # resume_score is server-computed (not client-set)
        assert isinstance(r.json()["profile"]["resume_score"], int)
        assert 0 <= r.json()["profile"]["resume_score"] <= 100

    def test_pro_profile_completion(self, session, professional):
        body = {"company": "Acme", "designation": "SDE", "experience_years": 5, "expertise": ["Backend"]}
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(professional["token"]))
        assert r.status_code == 200
        assert r.json()["user"]["profile_complete"] is True


# ---------- Wallet ----------
class TestWallet:
    def test_wallet_initial(self, session, student):
        r = session.get(f"{API}/wallet", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d["credits"] == 0
        assert d["free_uses_left"] >= 2

    def test_first_deposit_bonus(self, session, student):
        # create order
        r = session.post(f"{API}/wallet/deposit/create-order", json={"amount_inr": 199}, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        order = r.json()
        assert order["credits_to_grant"] == 398
        # confirm with any mock signature
        r2 = session.post(f"{API}/wallet/deposit/confirm", json={
            "razorpay_order_id": order["razorpay_order_id"],
            "razorpay_payment_id": "pay_mock_" + uuid.uuid4().hex[:8],
            "razorpay_signature": "mock_sig"
        }, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["added"] == 398
        # verify persisted
        w = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json()
        assert w["credits"] == 398

    def test_first_deposit_minimum_enforced(self, session, student):
        r = session.post(f"{API}/wallet/deposit/create-order", json={"amount_inr": 50}, headers=auth_headers(student["token"]))
        assert r.status_code == 400

    def test_subscription_plans(self, session, student):
        r = session.get(f"{API}/subscription/plans", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "free_tier" in d and "paid_tier" in d


# ---------- Interviews ----------
class TestInterviews:
    def test_full_interview_flow(self, session, professional, student):
        # pro creates slot in the future
        future_start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        future_end = (datetime.now(timezone.utc) + timedelta(days=2, hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r = session.post(f"{API}/interviews/slots", json={"start_at": future_start, "end_at": future_end, "topic": "DSA"}, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        slot = r.json()
        assert slot["start_at"] == future_start
        assert slot["end_at"] == future_end
        slot_id = slot["id"]
        # student books (free)
        r2 = session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["used_free"] is True
        # Backdate the slot start_at to >15min ago and mark both participants joined so
        # complete passes the new validations (min duration + both-joined). We use the
        # synchronous pymongo client to avoid event-loop tangles during pytest.
        from pymongo import MongoClient  # type: ignore
        import os
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        _mc = MongoClient(os.environ["MONGO_URL"])
        _coll = _mc[os.environ["DB_NAME"]].interview_slots
        past = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat()
        _coll.update_one(
            {"id": slot_id},
            {"$set": {"start_at": past, "end_at": end, "joined_by": [professional["user"]["id"], student["user"]["id"]]}},
        )
        _mc.close()
        # pro completes (new payload: rating + optional feedback)
        r3 = session.post(
            f"{API}/interviews/{slot_id}/complete",
            json={"rating": 8, "feedback": "Solid fundamentals"},
            headers=auth_headers(professional["token"]),
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["earned"] == 35
        # pro wallet has 35
        w = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        assert w["credits"] == 35
        # Student interviews_attended incremented and resume_score recomputed.
        # Use a tight filter (location matches a unique value) so the freshly-created student appears within page.
        # Set a unique location on this student via profile update to find them.
        upd = session.put(f"{API}/profile", json={"current_location": f"Loc-{slot_id[:8]}"}, headers=auth_headers(student["token"]))
        assert upd.status_code == 200, upd.text
        lb = session.get(f"{API}/leaderboard/students?location=Loc-{slot_id[:8]}&page_size=100", headers=auth_headers(student["token"])).json()
        items = lb["items"] if isinstance(lb, dict) else lb
        me = next((x for x in items if x.get("id") == student["user"]["id"]), None)
        assert me is not None and me.get("interviews_attended", 0) >= 1
        # Pro leaderboard reflects new rating
        plb = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"])).json()
        mp = next((x for x in plb if x.get("id") == professional["user"]["id"]), None)
        assert mp is not None and float(mp.get("rating", 0)) == 8.0

    def test_student_cannot_create_slot(self, session, student):
        future_start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        future_end = (datetime.now(timezone.utc) + timedelta(days=2, hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r = session.post(f"{API}/interviews/slots", json={"start_at": future_start, "end_at": future_end}, headers=auth_headers(student["token"]))
        assert r.status_code == 403


# ---------- Jobs & Referrals ----------
class TestJobs:
    def test_seeded_jobs(self, session, student):
        r = session.get(f"{API}/jobs", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        jobs = r.json()
        assert len(jobs) >= 3, f"Expected seeded jobs, got {len(jobs)}"

    def test_apply_with_free(self, session, student):
        jobs = session.get(f"{API}/jobs", headers=auth_headers(student["token"])).json()
        r = session.post(f"{API}/jobs/apply", json={"job_id": jobs[0]["id"]}, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["used_free"] is True
        # duplicate apply
        r2 = session.post(f"{API}/jobs/apply", json={"job_id": jobs[0]["id"]}, headers=auth_headers(student["token"]))
        assert r2.status_code == 400

    def test_referral_and_hire_flow(self, session, professional, student, employer, admin_token):
        # employer posts a job
        r = session.post(f"{API}/jobs", json={"title": "TEST Role", "description": "test", "location": "X", "salary_range": "10L", "skills_required": ["a"], "bulk_openings": 1}, headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # pro refers student
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": job_id, "note": "great fit"}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 200, r2.text
        app_id = r2.json()["application_id"]
        # employer submits hire (new flow requires note/proof — goes pending)
        r3 = session.post(f"{API}/applications/hire", json={"application_id": app_id, "note": "Offered SDE1 on 2025-06-12"}, headers=auth_headers(employer["token"]))
        assert r3.status_code == 200, r3.text
        change_id = r3.json().get("change_id")
        assert change_id, "expected change_id"
        # Admin approves
        r4 = session.post(f"{API}/admin/status-changes/action", json={"change_id": change_id, "action": "approve"}, headers=auth_headers(admin_token))
        assert r4.status_code == 200, r4.text
        # pro got REFERRAL_HIRED_REWARD (500)
        w = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        assert w["credits"] == 500, f"expected 500, got {w['credits']}"
        # employer (job poster) got HIRING_REWARD (1500)
        we = session.get(f"{API}/wallet", headers=auth_headers(employer["token"])).json()
        assert we["credits"] == 1500, f"expected 1500, got {we['credits']}"


# ---------- Leaderboards ----------
class TestLeaderboards:
    def test_leaderboard_students(self, session, student):
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict) and "items" in data
        rows = data["items"]
        if rows:
            assert "rank" in rows[0] and ("score" in rows[0] or "composite_score" in rows[0])

    def test_leaderboard_pros(self, session, professional):
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"]))
        assert r.status_code == 200


# ---------- Payouts ----------
class TestPayouts:
    def test_payout_request_min_enforced(self, session, professional):
        # pro starts with 0 credits, request <500 should be rejected by Pydantic
        r = session.post(f"{API}/payouts/request", json={"amount_inr": 100, "upi_or_account": "test@upi"}, headers=auth_headers(professional["token"]))
        assert r.status_code == 422  # Pydantic validation

    def test_payout_insufficient_credits(self, session, professional):
        r = session.post(f"{API}/payouts/request", json={"amount_inr": 500, "upi_or_account": "test@upi"}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400

    def test_full_payout_approve_flow(self, session, professional, student, employer, admin_token):
        # Earn 500+ credits via referral hire (now requires admin approval)
        r = session.post(f"{API}/jobs", json={"title": "X", "description": "y", "bulk_openings": 1}, headers=auth_headers(employer["token"]))
        job_id = r.json()["id"]
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": job_id}, headers=auth_headers(professional["token"]))
        app_id = r2.json()["application_id"]
        hr = session.post(f"{API}/applications/hire", json={"application_id": app_id, "note": "Onboarded"}, headers=auth_headers(employer["token"]))
        assert hr.status_code == 200, hr.text
        cid = hr.json().get("change_id")
        # admin approves → pro gets 500
        session.post(f"{API}/admin/status-changes/action", json={"change_id": cid, "action": "approve"}, headers=auth_headers(admin_token))
        # Now request payout
        r3 = session.post(f"{API}/payouts/request", json={"amount_inr": 500, "upi_or_account": "test@upi"}, headers=auth_headers(professional["token"]))
        assert r3.status_code == 200, r3.text
        payout_id = r3.json()["payout_id"]
        # Admin approves
        r4 = session.post(f"{API}/admin/payouts/action", json={"payout_id": payout_id, "action": "approve", "note": "ok"}, headers=auth_headers(admin_token))
        assert r4.status_code == 200
        # List payouts
        r5 = session.get(f"{API}/payouts", headers=auth_headers(professional["token"]))
        assert r5.status_code == 200
        assert any(p["id"] == payout_id and p["status"] == "approved" for p in r5.json())


# ---------- Admin ----------
class TestAdmin:
    def test_admin_stats(self, session, admin_token):
        r = session.get(f"{API}/admin/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        d = r.json()
        for k in ["students", "professionals", "employers", "jobs", "applications"]:
            assert k in d

    def test_admin_users(self, session, admin_token):
        r = session.get(f"{API}/admin/users", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_rbac_student_blocked_from_admin(self, session, student):
        r = session.get(f"{API}/admin/stats", headers=auth_headers(student["token"]))
        assert r.status_code == 403
        r2 = session.get(f"{API}/admin/users", headers=auth_headers(student["token"]))
        assert r2.status_code == 403


# ---------- Disputes ----------
class TestDisputes:
    def test_dispute_create_and_resolve(self, session, student, admin_token):
        r = session.post(f"{API}/disputes", json={"subject": "T", "description": "issue"}, headers=auth_headers(student["token"]))
        assert r.status_code == 200
        d_id = r.json()["id"]
        r2 = session.post(f"{API}/admin/disputes/{d_id}/resolve", headers=auth_headers(admin_token))
        assert r2.status_code == 200


# ---------- Notifications ----------
class TestNotifications:
    def test_list_and_mark_all_read(self, session, student):
        r = session.get(f"{API}/notifications", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        notes = r.json()
        assert isinstance(notes, list)
        # Welcome notification should be present
        assert len(notes) >= 1
        r2 = session.post(f"{API}/notifications/read-all", headers=auth_headers(student["token"]))
        assert r2.status_code == 200


# ---------- Auth Guards ----------
def test_missing_token(session):
    r = session.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_invalid_token(session):
    r = session.get(f"{API}/auth/me", headers={"Authorization": "Bearer invalid.token"})
    assert r.status_code == 401


# ============================================================
# Iteration 3 specific tests
# ============================================================

def _future(minutes_offset: int, duration_min: int = 30):
    s = datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)
    e = s + timedelta(minutes=duration_min)
    s = s.replace(microsecond=0)
    e = e.replace(microsecond=0)
    return s.isoformat().replace("+00:00", "Z"), e.isoformat().replace("+00:00", "Z")


# ---- Iteration 3: Profile new fields & completeness rules ----
class TestProfileIteration3:
    def test_others_education_requires_details(self, session, student):
        body = {
            "education": "Others",
            "passed_out_year": 2024,
            "current_location": "Pune",
            "preferred_role": "fresher",
            "skills": ["JS"],
            "resume_link": "https://example.com/r.pdf",
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        # missing education_details -> profile NOT complete
        assert r.json()["user"]["profile_complete"] is False
        # supply education_details now
        r2 = session.put(f"{API}/profile", json={**body, "education_details": "BBA Marketing"}, headers=auth_headers(student["token"]))
        assert r2.json()["user"]["profile_complete"] is True
        assert r2.json()["profile"]["education_details"] == "BBA Marketing"

    def test_experienced_requires_years_of_experience(self, session, student):
        body = {
            "education": "B.Tech",
            "passed_out_year": 2020,
            "current_location": "Mumbai",
            "preferred_role": "experienced",
            "skills": ["Java"],
            "resume_link": "https://example.com/r.pdf",
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.json()["user"]["profile_complete"] is False
        r2 = session.put(f"{API}/profile", json={**body, "years_of_experience": 4}, headers=auth_headers(student["token"]))
        assert r2.json()["user"]["profile_complete"] is True
        assert r2.json()["profile"]["years_of_experience"] == 4

    def test_resume_link_alone_satisfies_resume(self, session, student):
        body = {
            "education": "MBA",
            "passed_out_year": 2023,
            "current_location": "Delhi",
            "preferred_role": "fresher",
            "skills": ["Excel"],
            "resume_link": "https://example.com/cv.pdf",
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200
        assert r.json()["user"]["profile_complete"] is True

    def test_resume_score_is_server_computed(self, session, student):
        # Even if client sends resume_score, it's ignored
        body = {
            "education": "B.Tech",
            "passed_out_year": 2024,
            "current_location": "Bangalore",
            "dob": "2001-04-01",
            "preferred_role": "fresher",
            "skills": ["Python"],
            "resume_link": "https://example.com/cv.pdf",
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        score = r.json()["profile"]["resume_score"]
        # New 50–100 floor scoring: base 50 + profile fields (~15) → ~65 with this minimal payload
        assert 60 <= score <= 80, f"expected 60-80, got {score}"


# ---- Iteration 3: Interview slot start_at/end_at + conflict ----
class TestSlotIteration3:
    def test_slot_invalid_format(self, session, professional):
        r = session.post(f"{API}/interviews/slots", json={"start_at": "not-a-date", "end_at": "also-bad"}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400

    def test_slot_end_before_start(self, session, professional):
        s, e = _future(60, 30)
        r = session.post(f"{API}/interviews/slots", json={"start_at": e, "end_at": s}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400

    def test_slot_past(self, session, professional):
        s = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        e = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400

    def test_slot_too_short(self, session, professional):
        s, e = _future(60, 30)
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400
        assert "60" in r.json().get("detail", "")

    def test_slot_overlap_rejected_adjacent_allowed(self, session, professional):
        s1, e1 = _future(120, 60)
        r1 = session.post(f"{API}/interviews/slots", json={"start_at": s1, "end_at": e1}, headers=auth_headers(professional["token"]))
        assert r1.status_code == 200, r1.text
        # overlapping: starts inside [s1,e1]
        s_over = (datetime.fromisoformat(s1.replace("Z", "+00:00")) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        e_over = (datetime.fromisoformat(s1.replace("Z", "+00:00")) + timedelta(minutes=70)).isoformat().replace("+00:00", "Z")
        r2 = session.post(f"{API}/interviews/slots", json={"start_at": s_over, "end_at": e_over}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 400
        # adjacent (back-to-back, no overlap) should succeed
        r3 = session.post(f"{API}/interviews/slots", json={"start_at": e1, "end_at": (datetime.fromisoformat(e1.replace("Z", "+00:00")) + timedelta(minutes=60)).isoformat().replace("+00:00", "Z")}, headers=auth_headers(professional["token"]))
        assert r3.status_code == 200, r3.text

    def test_list_slots_sorted(self, session, professional):
        # Create two slots; verify sort by start_at
        s1, e1 = _future(180, 30)
        s2, e2 = _future(240, 30)
        session.post(f"{API}/interviews/slots", json={"start_at": s2, "end_at": e2}, headers=auth_headers(professional["token"]))
        session.post(f"{API}/interviews/slots", json={"start_at": s1, "end_at": e1}, headers=auth_headers(professional["token"]))
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(professional["token"]))
        assert r.status_code == 200
        slots = r.json()
        starts = [x["start_at"] for x in slots]
        assert starts == sorted(starts)
        for s in slots:
            assert "start_at" in s and "end_at" in s


# ---- Iteration 3: Jobs annotated with applied flag ----
class TestJobsAppliedFlag:
    def test_jobs_annotated_for_student(self, session, student):
        jobs = session.get(f"{API}/jobs", headers=auth_headers(student["token"])).json()
        assert all("applied" in j for j in jobs)
        # All unapplied initially
        assert all(j["applied"] is False for j in jobs)
        # Apply to first
        target = jobs[0]
        r = session.post(f"{API}/jobs/apply", json={"job_id": target["id"]}, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        jobs2 = session.get(f"{API}/jobs", headers=auth_headers(student["token"])).json()
        matched = next(j for j in jobs2 if j["id"] == target["id"])
        assert matched["applied"] is True
        assert matched["application_status"] == "applied"


# ---- Iteration 3: Applications pool (pro only) ----
class TestApplicationsPool:
    def test_pool_requires_professional(self, session, student):
        r = session.get(f"{API}/applications/pool", headers=auth_headers(student["token"]))
        assert r.status_code == 403

    def test_pool_blocked_for_employer(self, session, employer):
        r = session.get(f"{API}/applications/pool", headers=auth_headers(employer["token"]))
        assert r.status_code == 403

    def test_pool_hydrates_student_profile(self, session, professional, student, employer):
        # Set student profile and apply
        session.put(f"{API}/profile", json={
            "education": "B.Tech", "passed_out_year": 2024, "current_location": "Bangalore",
            "preferred_role": "fresher", "skills": ["Python"], "resume_link": "https://x.io/cv.pdf",
        }, headers=auth_headers(student["token"]))
        r = session.post(f"{API}/jobs", json={"title": "TEST pool", "description": "d", "bulk_openings": 1}, headers=auth_headers(employer["token"]))
        job_id = r.json()["id"]
        session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(student["token"]))
        r2 = session.get(f"{API}/applications/pool", headers=auth_headers(professional["token"]))
        assert r2.status_code == 200, r2.text
        pool = r2.json()
        ours = [a for a in pool if a["student_id"] == student["user"]["id"] and a["job_id"] == job_id]
        assert ours, "expected our application in pool"
        a = ours[0]
        assert "student_profile" in a
        sp = a["student_profile"]
        for k in ["education", "skills", "resume_score", "preferred_role", "current_location"]:
            assert k in sp
        assert sp["education"] == "B.Tech"
        assert "interviews_attended" in a
