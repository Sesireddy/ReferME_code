"""Iter 60 — Phone OTP verify normalisation fix.

Tests the /api/profile/phone/send-otp + /api/profile/phone/verify-otp pair after
the fix that normalises the incoming phone on verify to match the E.164 row
saved on send. Also covers negative + regression paths.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

TEST_PHONE_RAW = "9525852855"
TEST_PHONE_E164 = "+919525852855"


# ---------- helpers ----------
def _signup_and_verify(role: str = "student") -> tuple[str, dict]:
    """Create a fresh user and return (jwt_token, user_dict)."""
    suffix = uuid.uuid4().hex[:8]
    if role == "student":
        email = f"TEST_iter60_{suffix}@example.com"
    else:
        email = f"TEST_iter60_{suffix}@acmecorp.io"
    payload = {
        "email": email,
        "password": "Passw0rd!",
        "name": "Iter60 Tester",
        "role": role,
    }
    r = requests.post(f"{API}/auth/signup", json=payload, timeout=15)
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text}"
    body = r.json()
    otp = body.get("mock_otp")
    assert otp, f"mock_otp missing in signup response: {body}"
    r2 = requests.post(
        f"{API}/auth/verify-otp",
        json={"email": email, "otp": otp, "purpose": "verify_email"},
        timeout=15,
    )
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    data = r2.json()
    return data["token"], data["user"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def student():
    token, user = _signup_and_verify("student")
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def pro():
    token, user = _signup_and_verify("professional")
    return {"token": token, "user": user}


# ---------- Test 1: normalised send + normalised verify (happy path) ----------
class TestPhoneOtpNormalizedSendNormalizedVerify:
    def test_happy_path_e164_e164(self):
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        send_body = r.json()
        assert send_body.get("phone") == TEST_PHONE_E164
        otp = send_body.get("mock_otp")
        assert otp and len(otp) == 6

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_E164, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        vb = r2.json()
        assert vb["profile"]["phone_verified"] is True
        assert vb["profile"]["phone"] == TEST_PHONE_E164


# ---------- Test 2: THE REPORTED BUG — E.164 send + RAW 10-digit verify ----------
class TestPhoneOtpNormalizedSendRawVerify:
    def test_reported_bug_scenario(self):
        """This is the exact user-reported flow that was failing before the fix."""
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        otp = r.json()["mock_otp"]

        # Verify with the RAW 10-digit form (what the frontend actually sends)
        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_RAW, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 200, (
            f"BUG REGRESSED — verify with raw phone failed: {r2.status_code} {r2.text}"
        )
        vb = r2.json()
        assert vb["profile"]["phone_verified"] is True
        # Backend should have persisted the E.164 normalised form
        assert vb["profile"]["phone"] == TEST_PHONE_E164

        # /auth/me reflects the update
        me = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
        assert me["profile"]["phone"] == TEST_PHONE_E164
        assert me["profile"]["phone_verified"] is True
        assert "Verify Mobile Number" not in me.get("missing_fields", [])


# ---------- Test 3: Raw send + Raw verify (send normalises internally) ----------
class TestPhoneOtpRawSendRawVerify:
    def test_raw_raw_flow(self):
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_RAW},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # send-side already normalises
        assert r.json()["phone"] == TEST_PHONE_E164
        otp = r.json()["mock_otp"]

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_RAW, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["profile"]["phone_verified"] is True
        assert r2.json()["profile"]["phone"] == TEST_PHONE_E164


# ---------- Test 4: Wrong OTP rejected ----------
class TestPhoneOtpWrongOtp:
    def test_wrong_otp_returns_400(self):
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200
        # send-side returned a real OTP — pick a definitely-wrong one
        wrong = "000000" if r.json()["mock_otp"] != "000000" else "111111"

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_E164, "otp": wrong},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 400
        assert r2.json().get("detail") == "Incorrect OTP"


# ---------- Test 5: Invalid phone rejected with exact copy ----------
class TestPhoneOtpInvalidPhone:
    def test_invalid_phone_on_verify(self):
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        # Send a valid OTP first so we have a live OTP row not consumed
        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200
        good_otp = r.json()["mock_otp"]

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": "12345", "otp": good_otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 400
        assert r2.json().get("detail") == "Please enter a valid 10-digit Indian mobile number."

        # OTP row must NOT be consumed — retry with correct phone should succeed
        r3 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_E164, "otp": good_otp},
            headers=h,
            timeout=15,
        )
        assert r3.status_code == 200, r3.text


# ---------- Test 6: Expired OTP rejected ----------
class TestPhoneOtpExpired:
    def test_expired_otp_rejected(self):
        """Manually expire the OTP row via server.now_ts manipulation is not possible
        externally, so we DB-patch the expires_at directly to the past."""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200
        otp = r.json()["mock_otp"]

        # Force the OTP row to be expired.
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        assert mongo_url and db_name, "MONGO_URL + DB_NAME required for expiry test"

        async def expire():
            cli = AsyncIOMotorClient(mongo_url)
            await cli[db_name].otps.update_many(
                {"phone": TEST_PHONE_E164, "purpose": "verify_phone", "consumed": False},
                {"$set": {"expires_at": int(time.time()) - 60}},
            )
            cli.close()

        asyncio.get_event_loop().run_until_complete(expire())

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_E164, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 400
        assert r2.json().get("detail") == "OTP invalid or expired"


# ---------- Test 7: Pro alternate-Gmail OTP still works (regression) ----------
class TestProGmailOtpRegression:
    def test_pro_gmail_send_verify(self, pro):
        h = _auth_headers(pro["token"])
        alt = f"iter60.alt.{uuid.uuid4().hex[:6]}@gmail.com"
        r = requests.post(
            f"{API}/pro/gmail/send-otp",
            json={"email": alt},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        otp = r.json().get("mock_otp")
        assert otp, r.text

        r2 = requests.post(
            f"{API}/pro/gmail/verify-otp",
            json={"email": alt, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("alternate_gmail") == alt


# ---------- Test 8: /auth/me profile_completion updates after phone verification ----------
class TestAuthMeAfterPhoneVerify:
    def test_missing_fields_drops_verify_mobile(self):
        token, _ = _signup_and_verify("student")
        h = _auth_headers(token)

        me_before = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
        assert "Verify Mobile Number" in me_before.get("missing_fields", [])
        completion_before = me_before["profile_completion"]

        r = requests.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": TEST_PHONE_E164},
            headers=h,
            timeout=15,
        )
        otp = r.json()["mock_otp"]

        r2 = requests.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": TEST_PHONE_RAW, "otp": otp},
            headers=h,
            timeout=15,
        )
        assert r2.status_code == 200, r2.text

        me_after = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
        assert me_after["profile"]["phone"] == TEST_PHONE_E164
        assert me_after["profile"]["phone_verified"] is True
        assert "Verify Mobile Number" not in me_after.get("missing_fields", [])
        # Completion should have gone up by roughly 1/11 ≈ 9 percentage points
        assert me_after["profile_completion"] > completion_before
