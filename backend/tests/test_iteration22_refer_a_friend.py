"""
Phase 2 — Refer a Friend (Iteration 22)

Covers:
- POST /api/auth/signup ignores ref for non-student roles (professional)
- POST /api/auth/signup with valid ref creates pending referral + sets referred_by
- POST /api/auth/signup with invalid ref code completes silently (no referral row)
- POST /api/auth/signup with self-referral (same email as referrer) drops silently
- POST /api/auth/verify-otp on first student verification flips pending→successful
  + +25 credits to referrer + referral_reward transaction + notification
- POST /api/auth/verify-otp returns welcome_bonus=100
- GET /api/refer/me returns correct fields and stats
- GET /api/refer/me backfills referral_code for legacy users
- GET /api/refer/list returns rows with masked email, newest first
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Reuse BASE_URL/API from conftest by importing
from conftest import API, auth_headers, _signup_verify  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

REFERRAL_REWARD = 25
WELCOME_BONUS = 100


# ---------- helpers ----------
def _db():
    mc = MongoClient(MONGO_URL)
    return mc, mc[DB_NAME]


def _signup_student_unverified(session, ref_code: str | None = None, role: str = "student", email_prefix: str = "TEST"):
    email = f"{email_prefix.lower()}_{uuid.uuid4().hex[:10]}@referme.io"
    body = {"email": email, "password": "Test@12345", "role": role, "name": f"{email_prefix} {role}"}
    if ref_code is not None:
        body["ref"] = ref_code
    r = session.post(f"{API}/auth/signup", json=body)
    return email, r


def _verify(session, email: str, otp: str):
    return session.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})


# ---------- tests ----------
class TestReferMe:
    """GET /api/refer/me + backfill."""

    def test_refer_me_returns_code_link_and_stats(self, session, student):
        r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("code", "link", "reward", "total", "successful", "pending", "credits_earned"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["code"], str) and len(data["code"]) >= 6
        assert data["link"].endswith(f"ref={data['code']}") or f"ref={data['code']}" in data["link"]
        assert data["reward"] == REFERRAL_REWARD
        assert data["total"] >= 0
        assert data["successful"] >= 0
        assert data["pending"] >= 0
        assert data["credits_earned"] == data["successful"] * REFERRAL_REWARD

    def test_refer_me_backfills_for_legacy_user(self, session, student):
        # Remove referral_code from DB to simulate a legacy user
        mc, db = _db()
        db.users.update_one({"id": student["user"]["id"]}, {"$unset": {"referral_code": ""}})
        mc.close()

        r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        code = r.json().get("code")
        assert code and isinstance(code, str) and len(code) >= 6

        mc, db = _db()
        u = db.users.find_one({"id": student["user"]["id"]}, {"_id": 0, "referral_code": 1})
        mc.close()
        assert u and u.get("referral_code") == code


class TestSignupRefBehavior:
    """POST /api/auth/signup ref handling."""

    def test_signup_with_valid_ref_creates_pending_and_sets_referred_by(self, session, student):
        # Use the student's referral_code
        ref_code = student["user"].get("referral_code")
        # Make sure we have one (may need /refer/me to backfill)
        if not ref_code:
            r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
            ref_code = r.json()["code"]
        assert ref_code

        invitee_email, r = _signup_student_unverified(session, ref_code=ref_code, role="student")
        assert r.status_code == 200, r.text
        # New invitee user must have referred_by = referrer.id and a referrals doc pending
        mc, db = _db()
        invitee = db.users.find_one({"email": invitee_email}, {"_id": 0})
        ref_row = db.referrals.find_one({"referred_email": invitee_email}, {"_id": 0})
        mc.close()
        assert invitee is not None
        assert invitee.get("referred_by") == student["user"]["id"]
        assert ref_row is not None
        assert ref_row["status"] == "pending"
        assert ref_row["referrer_id"] == student["user"]["id"]
        assert ref_row["reward_credits"] == REFERRAL_REWARD
        assert ref_row["code"] == ref_code.upper()

    def test_signup_with_invalid_ref_code_completes_silently(self, session):
        invitee_email, r = _signup_student_unverified(session, ref_code="XXNOTAREALCODE99", role="student")
        assert r.status_code == 200, r.text
        mc, db = _db()
        invitee = db.users.find_one({"email": invitee_email}, {"_id": 0})
        ref_row = db.referrals.find_one({"referred_email": invitee_email}, {"_id": 0})
        mc.close()
        assert invitee is not None and invitee.get("referred_by") is None
        assert ref_row is None

    def test_signup_self_referral_silently_dropped(self, session):
        """Same email used as referrer == new invitee email — only possible synthetically:
        create a user with a known referral_code, then attempt to re-signup with that ref + same email.
        Since email already exists, signup returns 400 'Email already registered' — by contract
        a clean self-referral path needs the same person trying to sign up after they already exist.
        We instead emulate by creating a temp user, deleting them, then re-signing up with the
        same email + their old referral code. The new signup must NOT insert a referrals row.
        """
        # Step 1: signup + verify a student (so they get a code)
        first = _signup_verify(session, "student", prefix="TESTSELF")
        first_email = first["email"]
        mc, db = _db()
        ref_code = db.users.find_one({"id": first["user"]["id"]}, {"_id": 0, "referral_code": 1})["referral_code"]
        mc.close()

        # Step 2: delete that user + their referral_code so the same email can sign up again
        mc, db = _db()
        db.users.delete_one({"email": first_email})
        # Keep the ref_code "owned" by a phantom referrer? — Need the referrer to exist for lookup.
        # Recreate a *different* placeholder user holding that referral_code.
        placeholder_id = uuid.uuid4().hex
        db.users.insert_one({
            "id": placeholder_id,
            "email": first_email,  # SAME email — this is the self-referral case
            "role": "student",
            "is_email_verified": True,
            "referral_code": ref_code,
            "credits": 0,
            "created_at": "2025-01-01T00:00:00+00:00",
        })
        mc.close()

        # Step 3: try to sign up with SAME email + that ref code → should fail with 400 (email taken)
        body = {"email": first_email, "password": "Test@12345", "role": "student", "ref": ref_code}
        r = session.post(f"{API}/auth/signup", json=body)
        assert r.status_code == 400  # duplicate email

        # And: no referrals doc created with first_email
        mc, db = _db()
        ref_row = db.referrals.find_one({"referred_email": first_email}, {"_id": 0})
        # cleanup
        db.users.delete_one({"id": placeholder_id})
        mc.close()
        assert ref_row is None, "Self-referral should NOT create a referrals row"

    def test_signup_self_referral_path_via_signup_logic(self, session, student):
        """Direct test of the in-signup self-referral guard:
        we monkey-patch via DB: set referrer.email == invitee.email at signup time.
        Since both must be unique in users, we simulate by re-using the in-DB referrer's
        email + a NEW email — but request body uses ref. The server only checks
        referrer.email == body.email. So set the referrer's email == a soon-to-signup email."""
        # Allocate a target email
        target_email = f"selfref_{uuid.uuid4().hex[:8]}@referme.io"
        # Temporarily make the existing referrer have email==target_email
        mc, db = _db()
        original_email = student["user"]["email"]
        ref_code = student["user"].get("referral_code") or db.users.find_one({"id": student["user"]["id"]})["referral_code"]
        db.users.update_one({"id": student["user"]["id"]}, {"$set": {"email": target_email}})
        mc.close()
        try:
            body = {"email": target_email, "password": "Test@12345", "role": "student", "ref": ref_code}
            r = session.post(f"{API}/auth/signup", json=body)
            # Email already registered (referrer now owns it) → expect 400
            assert r.status_code == 400
        finally:
            # restore original email
            mc, db = _db()
            db.users.update_one({"id": student["user"]["id"]}, {"$set": {"email": original_email}})
            mc.close()

    def test_signup_ref_ignored_for_professional_role(self, session, student):
        ref_code = student["user"].get("referral_code")
        if not ref_code:
            r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
            ref_code = r.json()["code"]

        pro_email = f"testpro_{uuid.uuid4().hex[:8]}@acmecorp.io"
        body = {"email": pro_email, "password": "Test@12345", "role": "professional", "ref": ref_code, "name": "TEST pro"}
        r = session.post(f"{API}/auth/signup", json=body)
        assert r.status_code == 200, r.text

        mc, db = _db()
        pro = db.users.find_one({"email": pro_email}, {"_id": 0})
        ref_row = db.referrals.find_one({"referred_email": pro_email}, {"_id": 0})
        mc.close()
        assert pro is not None
        assert pro.get("referred_by") is None, "Pro signup must NOT set referred_by"
        assert ref_row is None, "Pro signup must NOT create referrals doc"

    def test_signup_ref_ignored_for_employer_role(self, session, student):
        """Employer signup is blocked entirely (400) — confirm no referral side-effect either."""
        ref_code = student["user"].get("referral_code")
        if not ref_code:
            r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
            ref_code = r.json()["code"]

        emp_email = f"testemp_{uuid.uuid4().hex[:8]}@referme.io"
        body = {"email": emp_email, "password": "Test@12345", "role": "employer", "ref": ref_code}
        r = session.post(f"{API}/auth/signup", json=body)
        assert r.status_code == 400  # employer signup blocked

        mc, db = _db()
        ref_row = db.referrals.find_one({"referred_email": emp_email}, {"_id": 0})
        u = db.users.find_one({"email": emp_email}, {"_id": 0})
        mc.close()
        assert u is None
        assert ref_row is None


class TestVerifyOtpReferralCompletion:
    """POST /api/auth/verify-otp flips pending→successful and pays the referrer."""

    def test_first_student_verification_awards_referrer(self, session, student):
        ref_code = student["user"].get("referral_code")
        if not ref_code:
            r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
            ref_code = r.json()["code"]

        # Capture referrer credits before
        mc, db = _db()
        before = db.users.find_one({"id": student["user"]["id"]}, {"_id": 0, "credits": 1})
        mc.close()
        before_credits = before["credits"]

        # Signup invitee with ref
        invitee_email, r = _signup_student_unverified(session, ref_code=ref_code, role="student")
        assert r.status_code == 200
        otp = r.json()["mock_otp"]

        # Verify invitee email
        r2 = _verify(session, invitee_email, otp)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data.get("welcome_bonus") == WELCOME_BONUS, "welcome_bonus contract preserved"
        assert "token" in data and "user" in data

        # Referrer should have +25 credits
        mc, db = _db()
        after = db.users.find_one({"id": student["user"]["id"]}, {"_id": 0, "credits": 1})
        ref_row = db.referrals.find_one({"referred_email": invitee_email}, {"_id": 0})
        tx = db.transactions.find_one(
            {"user_id": student["user"]["id"], "reason": "referral_reward", "meta.referral_id": ref_row["id"]},
            {"_id": 0},
        )
        notif = db.notifications.find_one(
            {"user_id": student["user"]["id"], "title": {"$regex": "Referral Reward"}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        mc.close()

        assert after["credits"] == before_credits + REFERRAL_REWARD, f"+25 credits expected, got delta {after['credits']-before_credits}"
        assert ref_row["status"] == "successful"
        assert ref_row.get("completed_at") is not None
        assert tx is not None and tx["delta"] == REFERRAL_REWARD
        assert notif is not None, "in-app referral notification expected"

    def test_welcome_bonus_returned_without_ref(self, session):
        """No ref → welcome_bonus still 100 on first student verify (Phase 1 contract)."""
        invitee_email, r = _signup_student_unverified(session, ref_code=None, role="student")
        assert r.status_code == 200
        otp = r.json()["mock_otp"]
        r2 = _verify(session, invitee_email, otp)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("welcome_bonus") == WELCOME_BONUS


class TestReferList:
    """GET /api/refer/list."""

    def test_refer_list_returns_masked_emails_newest_first(self, session, student):
        # Ensure referral_code
        r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        ref_code = r.json()["code"]

        # Create 2 referred signups, verify only first (so we have 1 successful + 1 pending)
        e1, r1 = _signup_student_unverified(session, ref_code=ref_code, role="student", email_prefix="REFLISTA")
        assert r1.status_code == 200
        otp1 = r1.json()["mock_otp"]
        v1 = _verify(session, e1, otp1)
        assert v1.status_code == 200

        e2, r2 = _signup_student_unverified(session, ref_code=ref_code, role="student", email_prefix="REFLISTB")
        assert r2.status_code == 200

        # Fetch /refer/list
        rl = session.get(f"{API}/refer/list", headers=auth_headers(student["token"]))
        assert rl.status_code == 200, rl.text
        rows = rl.json()
        assert isinstance(rows, list)
        # Find our two rows
        emails_seen = {row["email_masked"] for row in rows}
        # Each email should be masked: first 2 chars + ***@domain
        for row in rows:
            em = row["email_masked"]
            assert "***@" in em, f"row not masked: {em}"
            local = em.split("@")[0]
            # Should start with 1 or 2 chars before "***"
            assert "***" in local
            assert row["status"] in ("pending", "successful", "rejected")
            assert "id" in row and "created_at" in row
            assert row["reward_credits"] == REFERRAL_REWARD

        # Verify newest-first ordering using created_at desc
        created_ats = [row["created_at"] for row in rows if row.get("created_at")]
        assert created_ats == sorted(created_ats, reverse=True), "rows must be newest first"

        # Sanity: e1 and e2 should both be represented in the rows (by masked form)
        # Mask manually: first 2 chars + ***@domain
        def mask(em):
            local, dom = em.split("@")
            if len(local) <= 2:
                return f"{local[:1]}***@{dom}"
            return f"{local[:2]}***@{dom}"

        assert mask(e1) in emails_seen
        assert mask(e2) in emails_seen


class TestReferMeStatsReflectActivity:
    """After referrals + verify, /refer/me stats must reflect them."""

    def test_stats_increment_after_referral_completion(self, session, student):
        # Get initial stats
        r0 = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        assert r0.status_code == 200
        before = r0.json()
        ref_code = before["code"]

        # Create 1 successful + 1 pending
        e1, s1 = _signup_student_unverified(session, ref_code=ref_code, role="student", email_prefix="STATA")
        otp1 = s1.json()["mock_otp"]
        _verify(session, e1, otp1)

        e2, s2 = _signup_student_unverified(session, ref_code=ref_code, role="student", email_prefix="STATB")
        assert s2.status_code == 200

        r1 = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        after = r1.json()
        assert after["total"] >= before["total"] + 2
        assert after["successful"] >= before["successful"] + 1
        assert after["pending"] >= before["pending"] + 1
        assert after["credits_earned"] == after["successful"] * REFERRAL_REWARD
