"""
Iteration 23 — Referral code validation on Job Seeker signup

Covers:
- GET /api/refer/validate with empty/missing → valid=true
- GET /api/refer/validate with a known valid code (USERECE1AD84 / seseendra) → valid=true + owner_name
- GET /api/refer/validate with bogus code → valid=false + canonical message
- GET /api/refer/validate with a suspended owner's code → valid=false + canonical message
- POST /api/auth/signup with ref=None or "" → succeeds, no referral row created, referred_by=None
- POST /api/auth/signup with ref=VALID → succeeds, creates pending referral row + sets referred_by
- POST /api/auth/signup with ref=BOGUS → HTTP 400 with canonical detail; NO user, NO referral row
- POST /api/auth/signup with ref to suspended user → HTTP 400 same canonical detail
- Phase 2 contract preserved: verify-otp still awards +25 to referrer and welcome_bonus=100
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from conftest import API, _signup_verify  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

CANONICAL_MSG = "Invalid referral code. Please check and try again."
REFERRAL_REWARD = 25
WELCOME_BONUS = 100

# Seed referral code documented in /app/memory/test_credentials.md style note
SEED_REF_CODE = "USERECE1AD84"


def _db():
    mc = MongoClient(MONGO_URL)
    return mc, mc[DB_NAME]


@pytest.fixture(scope="module")
def seed_owner():
    """Ensure a user with referral_code=USERECE1AD84 exists and is active.
    If absent (clean db), create one so tests are self-contained.
    """
    mc, db = _db()
    try:
        owner = db.users.find_one({"referral_code": SEED_REF_CODE}, {"_id": 0})
        if not owner:
            from passlib.context import CryptContext
            pw_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash("Test@12345")
            owner = {
                "id": uuid.uuid4().hex,
                "email": "seseendra@referme.io",
                "role": "student",
                "name": "seseendra",
                "password_hash": pw_hash,
                "is_email_verified": True,
                "account_status": "active",
                "credits": 0,
                "free_uses_left": 0,
                "total_deposits": 0,
                "profile_complete": False,
                "profile": {},
                "referral_code": SEED_REF_CODE,
                "referred_by": None,
                "created_at": "2025-01-01T00:00:00+00:00",
            }
            db.users.insert_one(owner)
        # Force active
        db.users.update_one({"referral_code": SEED_REF_CODE}, {"$set": {"account_status": "active"}})
        yield owner
    finally:
        mc.close()


# ============== GET /refer/validate ==============
class TestReferValidate:
    def test_empty_code_is_valid(self, session):
        r = session.get(f"{API}/refer/validate", params={"code": ""})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("valid") is True
        assert "message" not in body or not body.get("message")

    def test_whitespace_code_is_valid(self, session):
        r = session.get(f"{API}/refer/validate", params={"code": "   "})
        assert r.status_code == 200, r.text
        assert r.json().get("valid") is True

    def test_valid_code_returns_owner_name(self, session, seed_owner):
        r = session.get(f"{API}/refer/validate", params={"code": SEED_REF_CODE})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("valid") is True
        assert body.get("owner_name"), f"Expected owner_name, got {body}"

    def test_valid_code_lowercased_input(self, session, seed_owner):
        """Server should upper-case + strip user input before lookup."""
        r = session.get(f"{API}/refer/validate", params={"code": SEED_REF_CODE.lower()})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("valid") is True
        assert body.get("owner_name")

    def test_bogus_code_returns_canonical_message(self, session):
        r = session.get(f"{API}/refer/validate", params={"code": "BOGUS12345"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("valid") is False
        assert body.get("message") == CANONICAL_MSG

    def test_suspended_owner_code_invalid(self, session, seed_owner):
        """If the owner's account_status != active → treated as invalid."""
        mc, db = _db()
        try:
            db.users.update_one({"referral_code": SEED_REF_CODE}, {"$set": {"account_status": "suspended"}})
            r = session.get(f"{API}/refer/validate", params={"code": SEED_REF_CODE})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("valid") is False
            assert body.get("message") == CANONICAL_MSG
        finally:
            # Restore
            db.users.update_one({"referral_code": SEED_REF_CODE}, {"$set": {"account_status": "active"}})
            mc.close()


# ============== POST /auth/signup with ref ==============
class TestSignupRefBehavior:
    def test_signup_without_ref_succeeds(self, session):
        email = f"test_noref_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={
            "email": email, "password": "Test@12345", "role": "student", "name": "No Ref"
        })
        assert r.status_code == 200, r.text
        # No referral row should exist for this user
        mc, db = _db()
        try:
            user = db.users.find_one({"email": email}, {"_id": 0})
            assert user is not None
            assert user.get("referred_by") is None
            ref_rows = list(db.referrals.find({"referred_email": email}, {"_id": 0}))
            assert ref_rows == [], f"Expected no referral rows, found {ref_rows}"
        finally:
            mc.close()

    def test_signup_with_empty_string_ref_succeeds(self, session):
        email = f"test_emptyref_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={
            "email": email, "password": "Test@12345", "role": "student", "name": "Empty Ref", "ref": ""
        })
        assert r.status_code == 200, r.text
        mc, db = _db()
        try:
            user = db.users.find_one({"email": email}, {"_id": 0})
            assert user is not None
            assert user.get("referred_by") is None
        finally:
            mc.close()

    def test_signup_with_valid_ref_creates_pending_referral(self, session, seed_owner):
        email = f"test_validref_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={
            "email": email, "password": "Test@12345", "role": "student",
            "name": "Valid Ref", "ref": SEED_REF_CODE,
        })
        assert r.status_code == 200, r.text
        mc, db = _db()
        try:
            user = db.users.find_one({"email": email}, {"_id": 0})
            assert user is not None
            assert user.get("referred_by") == seed_owner["id"]
            row = db.referrals.find_one({"referred_email": email}, {"_id": 0})
            assert row is not None, "Expected a referral row to be created"
            assert row.get("status") == "pending"
            assert row.get("reward_credits") == REFERRAL_REWARD
            assert row.get("code") == SEED_REF_CODE
        finally:
            mc.close()

    def test_signup_with_bogus_ref_returns_400_and_no_user(self, session):
        email = f"test_bogusref_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(f"{API}/auth/signup", json={
            "email": email, "password": "Test@12345", "role": "student",
            "name": "Bogus Ref", "ref": "BOGUS99999",
        })
        assert r.status_code == 400, r.text
        body = r.json()
        assert body.get("detail") == CANONICAL_MSG, body
        # CRITICAL: ensure no user and no referral row were persisted
        mc, db = _db()
        try:
            assert db.users.find_one({"email": email}, {"_id": 0}) is None, "User should not be created on invalid ref"
            assert db.referrals.find_one({"referred_email": email}, {"_id": 0}) is None
        finally:
            mc.close()

    def test_signup_with_suspended_owner_ref_returns_400(self, session, seed_owner):
        email = f"test_suspref_{uuid.uuid4().hex[:8]}@referme.io"
        mc, db = _db()
        try:
            db.users.update_one({"referral_code": SEED_REF_CODE}, {"$set": {"account_status": "suspended"}})
            r = session.post(f"{API}/auth/signup", json={
                "email": email, "password": "Test@12345", "role": "student",
                "name": "Susp Ref", "ref": SEED_REF_CODE,
            })
            assert r.status_code == 400, r.text
            assert r.json().get("detail") == CANONICAL_MSG
            assert db.users.find_one({"email": email}, {"_id": 0}) is None
            assert db.referrals.find_one({"referred_email": email}, {"_id": 0}) is None
        finally:
            db.users.update_one({"referral_code": SEED_REF_CODE}, {"$set": {"account_status": "active"}})
            mc.close()


# ============== Phase 2 verify-otp contract preserved ==============
class TestVerifyOtpReferralCompletion:
    def test_verify_otp_awards_referrer_and_returns_welcome_bonus(self, session, seed_owner):
        """Full E2E: signup with valid ref → verify-otp → referrer +25, new student welcome_bonus=100."""
        mc, db = _db()
        try:
            owner_before = db.users.find_one({"id": seed_owner["id"]}, {"_id": 0})
            credits_before = int(owner_before.get("credits") or 0)

            email = f"test_e2e_{uuid.uuid4().hex[:8]}@referme.io"
            r = session.post(f"{API}/auth/signup", json={
                "email": email, "password": "Test@12345", "role": "student",
                "name": "E2E Ref", "ref": SEED_REF_CODE,
            })
            assert r.status_code == 200, r.text
            otp = r.json().get("mock_otp")
            assert otp, "mock_otp must be returned in TEST_RETURN_OTP mode"

            r2 = session.post(f"{API}/auth/verify-otp", json={
                "email": email, "otp": otp, "purpose": "verify_email"
            })
            assert r2.status_code == 200, r2.text
            data = r2.json()

            # welcome_bonus contract
            assert data.get("welcome_bonus") == WELCOME_BONUS, data

            # Referrer should now have +25 credits
            owner_after = db.users.find_one({"id": seed_owner["id"]}, {"_id": 0})
            credits_after = int(owner_after.get("credits") or 0)
            assert credits_after == credits_before + REFERRAL_REWARD, (
                f"Expected {credits_before + REFERRAL_REWARD}, got {credits_after}"
            )

            # Referral row flipped to successful
            row = db.referrals.find_one({"referred_email": email}, {"_id": 0})
            assert row is not None
            assert row.get("status") == "successful"
        finally:
            mc.close()
