"""Phase B: Mobile phone (mock SMS) OTP flow + PUT /profile phone_verified guards."""
import uuid
import pytest
from conftest import API, auth_headers


# --- send-otp ---
class TestPhoneSendOtp:
    def test_send_otp_requires_auth(self, session):
        r = session.post(f"{API}/profile/phone/send-otp", json={"phone": "+919876543210"})
        assert r.status_code == 401

    def test_send_otp_valid_phone(self, session, student):
        r = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": "+919876543210"},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phone") == "+919876543210"
        otp = body.get("mock_otp")
        assert otp and len(otp) == 6 and otp.isdigit(), f"expected 6-digit mock_otp, got {otp!r}"

    def test_send_otp_invalid_phone(self, session, student):
        r = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": "abc"},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 400


# --- verify-otp ---
class TestPhoneVerifyOtp:
    def test_verify_otp_success_sets_phone_verified(self, session, student):
        phone = "+919876500001"
        s = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": phone},
            headers=auth_headers(student["token"]),
        )
        otp = s.json()["mock_otp"]
        v = session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": phone, "otp": otp},
            headers=auth_headers(student["token"]),
        )
        assert v.status_code == 200, v.text
        prof = v.json().get("profile", {})
        assert prof.get("phone") == phone
        assert prof.get("phone_verified") is True
        # GET /auth/me — confirm persisted
        me = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
        assert me.status_code == 200
        mp = me.json().get("profile", {})
        assert mp.get("phone") == phone
        assert mp.get("phone_verified") is True

    def test_verify_otp_wrong_otp(self, session, student):
        phone = "+919876500002"
        session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": phone},
            headers=auth_headers(student["token"]),
        )
        v = session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": phone, "otp": "000000"},
            headers=auth_headers(student["token"]),
        )
        assert v.status_code == 400
        assert "Incorrect OTP" in v.json().get("detail", "")

    def test_verify_otp_unknown_phone(self, session, student):
        v = session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": "+910000000000", "otp": "123456"},
            headers=auth_headers(student["token"]),
        )
        assert v.status_code == 400
        assert "invalid or expired" in v.json().get("detail", "").lower()

    def test_verify_otp_requires_auth(self, session):
        r = session.post(f"{API}/profile/phone/verify-otp", json={"phone": "+919", "otp": "111111"})
        assert r.status_code == 401


# --- PUT /profile guard rails ---
class TestPhoneVerifiedProfileGuards:
    def test_phone_change_resets_verified(self, session, student):
        phone = "+919876500010"
        # Verify phone first
        s = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": phone},
            headers=auth_headers(student["token"]),
        )
        otp = s.json()["mock_otp"]
        session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": phone, "otp": otp},
            headers=auth_headers(student["token"]),
        )
        # confirm verified
        me = session.get(f"{API}/auth/me", headers=auth_headers(student["token"])).json()
        assert me["profile"]["phone_verified"] is True

        # Now PUT /profile with a DIFFERENT phone — phone_verified must flip to False
        new_phone = "+919876500099"
        r = session.put(
            f"{API}/profile",
            json={"phone": new_phone},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        prof = r.json()["profile"]
        assert prof.get("phone") == new_phone
        assert prof.get("phone_verified") is False

    def test_phone_unchanged_keeps_verified(self, session, student):
        phone = "+919876500020"
        s = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": phone},
            headers=auth_headers(student["token"]),
        )
        otp = s.json()["mock_otp"]
        session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": phone, "otp": otp},
            headers=auth_headers(student["token"]),
        )
        # PUT /profile with SAME phone — phone_verified must remain True
        r = session.put(
            f"{API}/profile",
            json={"phone": phone, "current_location": "Hyderabad"},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        prof = r.json()["profile"]
        assert prof.get("phone_verified") is True

    def test_client_supplied_phone_verified_ignored(self, session, student):
        # Without ever verifying, attempt to set phone_verified=true via PUT /profile
        r = session.put(
            f"{API}/profile",
            json={"phone": "+919876500030", "phone_verified": True},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        prof = r.json()["profile"]
        # SECURITY: client-supplied phone_verified must be ignored
        assert prof.get("phone_verified") is False, (
            f"phone_verified must NOT be settable via PUT /profile; got {prof.get('phone_verified')!r}"
        )

    def test_client_supplied_phone_verified_ignored_when_already_verified(self, session, student):
        phone = "+919876500040"
        s = session.post(
            f"{API}/profile/phone/send-otp",
            json={"phone": phone},
            headers=auth_headers(student["token"]),
        )
        otp = s.json()["mock_otp"]
        session.post(
            f"{API}/profile/phone/verify-otp",
            json={"phone": phone, "otp": otp},
            headers=auth_headers(student["token"]),
        )
        # Try to flip phone_verified=False via PUT — must stay True (client value ignored)
        r = session.put(
            f"{API}/profile",
            json={"phone": phone, "phone_verified": False},
            headers=auth_headers(student["token"]),
        )
        prof = r.json()["profile"]
        assert prof.get("phone_verified") is True


# --- Regression: existing endpoints still work ---
class TestPhaseBRegression:
    def test_health(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200

    def test_me_works(self, session, student):
        r = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200

    def test_jobs_list_works(self, session, student):
        r = session.get(f"{API}/jobs", headers=auth_headers(student["token"]))
        assert r.status_code == 200

    def test_wallet_works(self, session, student):
        r = session.get(f"{API}/wallet", headers=auth_headers(student["token"]))
        assert r.status_code == 200

    def test_leaderboard_works(self, session, student):
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200
