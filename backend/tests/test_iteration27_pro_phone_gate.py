"""Iteration 27: Pro phone-verified gate on slots/jobs/redemption + PUT /profile validation."""
from datetime import datetime, timedelta, timezone
import pytest
from conftest import API, auth_headers


PRO_PHONE_GATE_MSG = (
    "Please add and verify your mobile number to continue. "
    "Go to Profile → Verify Mobile Number."
)


# Helper to verify phone for a pro via mock OTP
def _verify_pro_phone(session, token, phone="+918989849312"):
    r = session.post(
        f"{API}/profile/phone/send-otp",
        json={"phone": phone},
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    v = session.post(
        f"{API}/profile/phone/verify-otp",
        json={"phone": phone, "otp": otp},
        headers=auth_headers(token),
    )
    assert v.status_code == 200, v.text
    return v.json().get("profile", {})


# ---------- PUT /profile validation (regression - already implemented) ----------
class TestProfilePhoneValidation:
    def test_short_phone_rejected(self, session, professional):
        r = session.put(
            f"{API}/profile",
            json={"phone": "12345"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 400, r.text
        assert "10-digit" in r.json()["detail"]

    def test_non_indian_country_code_rejected(self, session, professional):
        r = session.put(
            f"{API}/profile",
            json={"phone": "+44 7700900900"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 400, r.text
        assert "+91" in r.json()["detail"]

    def test_invalid_first_digit_rejected(self, session, professional):
        r = session.put(
            f"{API}/profile",
            json={"phone": "5989849312"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 400, r.text
        assert "6, 7, 8, or 9" in r.json()["detail"]

    def test_valid_phone_normalized_and_unverified(self, session, professional):
        r = session.put(
            f"{API}/profile",
            json={"phone": "8989849312"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        prof = r.json()["profile"]
        assert prof.get("phone") == "+918989849312"
        assert prof.get("phone_verified") is False


# ---------- /interviews/slots gate ----------
class TestSlotsPhoneGate:
    def _slot_body(self):
        # tomorrow 10:00 - 10:30 IST in ISO
        start = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
        end = start + timedelta(minutes=30)
        return {
            "title": "TEST_iter27 slot",
            "skill_set": ["Python"],
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        }

    def test_pro_without_verified_phone_blocked(self, session, professional):
        r = session.post(
            f"{API}/interviews/slots",
            json=self._slot_body(),
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == PRO_PHONE_GATE_MSG

    def test_pro_with_verified_phone_allowed(self, session, professional):
        _verify_pro_phone(session, professional["token"], phone="+919876510027")
        r = session.post(
            f"{API}/interviews/slots",
            json=self._slot_body(),
            headers=auth_headers(professional["token"]),
        )
        # Should pass the phone gate. May fail later on title/skill_set/etc.
        # but must NOT be a 403 PRO_PHONE_GATE_MSG.
        if r.status_code == 403:
            assert r.json().get("detail") != PRO_PHONE_GATE_MSG, r.text
        # Most likely 200
        assert r.status_code in (200, 400), r.text


# ---------- /jobs gate ----------
class TestJobsPhoneGate:
    def _job_body(self):
        return {
            "title": "TEST_iter27 job",
            "description": "test job desc",
            "location": "Bengaluru",
            "skills_required": ["Python"],
            "company": "TEST Corp",
            "open_positions_label": "1",
        }

    def test_pro_without_verified_phone_blocked(self, session, professional):
        r = session.post(
            f"{API}/jobs",
            json=self._job_body(),
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == PRO_PHONE_GATE_MSG

    def test_pro_with_verified_phone_allowed(self, session, professional):
        _verify_pro_phone(session, professional["token"], phone="+919876510028")
        r = session.post(
            f"{API}/jobs",
            json=self._job_body(),
            headers=auth_headers(professional["token"]),
        )
        # Should not be phone gated; jobs may have credit requirement etc.
        if r.status_code == 403:
            assert r.json().get("detail") != PRO_PHONE_GATE_MSG, r.text
        assert r.status_code in (200, 400, 402), r.text

    def test_employer_not_phone_gated(self, session, employer):
        # employers should be unaffected by the pro-only phone gate
        r = session.post(
            f"{API}/jobs",
            json=self._job_body(),
            headers=auth_headers(employer["token"]),
        )
        # Must NOT be the phone-gate 403
        if r.status_code == 403:
            assert r.json().get("detail") != PRO_PHONE_GATE_MSG, r.text
        assert r.status_code in (200, 400, 402), r.text


# ---------- /redemption/submit gate ----------
class TestRedemptionPhoneGate:
    def _body(self, credits=1000):
        return {"upi_id": "test@upi", "credits": credits, "account_holder_name": "TEST Holder"}

    def test_pro_without_verified_phone_blocked(self, session, professional):
        r = session.post(
            f"{API}/redemption/submit",
            json=self._body(),
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == PRO_PHONE_GATE_MSG

    def test_pro_with_verified_phone_passes_gate(self, session, professional):
        _verify_pro_phone(session, professional["token"], phone="+919876510029")
        # The pro has 0 credits so this will fail on credit checks — but NOT the phone gate
        r = session.post(
            f"{API}/redemption/submit",
            json=self._body(credits=1000),
            headers=auth_headers(professional["token"]),
        )
        # Either 400 (min credits / amount exceeds avail) — should NOT be 403 phone gate
        if r.status_code == 403:
            assert r.json().get("detail") != PRO_PHONE_GATE_MSG, r.text
        assert r.status_code != 403 or r.json().get("detail") != PRO_PHONE_GATE_MSG
