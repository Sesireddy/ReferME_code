"""Comprehensive backend tests for ReferME API.
Covers: health, auth, profile, wallet, interviews, jobs, referrals,
leaderboards, payouts, admin, disputes, notifications, RBAC.
"""
import os
import time
import uuid
import requests
import pytest
from conftest import API, auth_headers


# ---------- Health ----------
def test_health(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data["app"] == "ReferME"
    assert data["mock_otp"] is True
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
        body = {"name": "S One", "education": "B.Tech CSE", "skills": ["Python"], "resume_base64": "data:application/pdf;base64,xx", "resume_score": 78}
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True
        assert r.json()["profile"]["resume_score"] == 78

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
        # pro creates slot
        r = session.post(f"{API}/interviews/slots", json={"scheduled_at": "2026-06-01T10:00:00Z", "topic": "DSA"}, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        slot = r.json()
        slot_id = slot["id"]
        # student books (free)
        r2 = session.post(f"{API}/interviews/book", json={"slot_id": slot_id}, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["used_free"] is True
        # pro completes
        r3 = session.post(f"{API}/interviews/{slot_id}/complete", headers=auth_headers(professional["token"]))
        assert r3.status_code == 200
        assert r3.json()["earned"] == 25
        # pro wallet has 25
        w = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        assert w["credits"] == 25

    def test_student_cannot_create_slot(self, session, student):
        r = session.post(f"{API}/interviews/slots", json={"scheduled_at": "2026-06-01T10:00:00Z"}, headers=auth_headers(student["token"]))
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

    def test_referral_and_hire_flow(self, session, professional, student, employer):
        # employer posts a job
        r = session.post(f"{API}/jobs", json={"title": "TEST Role", "description": "test", "location": "X", "salary_range": "10L", "skills_required": ["a"], "bulk_openings": 1}, headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # pro refers student
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": job_id, "note": "great fit"}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 200, r2.text
        app_id = r2.json()["application_id"]
        # employer hires
        r3 = session.post(f"{API}/applications/hire", json={"application_id": app_id}, headers=auth_headers(employer["token"]))
        assert r3.status_code == 200
        # pro got +500
        w = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        assert w["credits"] == 500


# ---------- Leaderboards ----------
class TestLeaderboards:
    def test_leaderboard_students(self, session, student):
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "rank" in data[0] and "score" in data[0]

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
        # Earn 500+ credits via referral hire
        r = session.post(f"{API}/jobs", json={"title": "X", "description": "y", "bulk_openings": 1}, headers=auth_headers(employer["token"]))
        job_id = r.json()["id"]
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": job_id}, headers=auth_headers(professional["token"]))
        app_id = r2.json()["application_id"]
        session.post(f"{API}/applications/hire", json={"application_id": app_id}, headers=auth_headers(employer["token"]))
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
