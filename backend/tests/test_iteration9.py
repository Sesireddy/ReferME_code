"""Iteration 9 backend tests — Mock Interview, Job Posting & Profile validations.

Covers:
- POST /api/interviews/slots gmail_verified gate (403, exact message)
- POST /api/interviews/slots empty skill_set (400, 'Skill Set is required.')
- POST /api/jobs mandatory-field guards (Job Title / Description / Location / Skill Set)
- POST /api/jobs open_positions_label accepted + persisted, default '1 to 5'
- GET /api/auth/me returns missing_fields[] (10 mandatory factors) for a fresh pro
- /pro/gmail/verify-otp drops 'Alternate Gmail Address' from missing_fields
"""
from __future__ import annotations

import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

# Import helpers from conftest (defined at module level there)
from conftest import API, _signup_verify, auth_headers  # type: ignore


def _future_iso(hours_from_now: int = 24, minutes: int = 60):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    end = start + timedelta(minutes=minutes)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


# ------------------- Mock Interview slot gating -------------------
class TestSlotCreationGmailGate:
    """POST /api/interviews/slots gmail_verified gate."""

    def test_slot_creation_requires_gmail_verified_403(self, session):
        # Raw professional (no _gmail_verify_in_db patch applied)
        pro = _signup_verify(session, "professional")
        start, end = _future_iso()
        r = session.post(
            f"{API}/interviews/slots",
            headers=auth_headers(pro["token"]),
            json={"start_at": start, "end_at": end, "skill_set": ["React"], "experience_years": 2},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Gmail verification is required before creating a Mock Interview slot."

    def test_slot_creation_empty_skill_set_400(self, session, professional):
        # professional fixture has gmail_verified=True
        start, end = _future_iso()
        r = session.post(
            f"{API}/interviews/slots",
            headers=auth_headers(professional["token"]),
            json={"start_at": start, "end_at": end, "skill_set": [], "experience_years": 2},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Skill Set is required."

    def test_slot_creation_omitted_skill_set_400(self, session, professional):
        start, end = _future_iso()
        r = session.post(
            f"{API}/interviews/slots",
            headers=auth_headers(professional["token"]),
            json={"start_at": start, "end_at": end, "experience_years": 2},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Skill Set is required."

    def test_slot_creation_success_with_gmail_and_skill(self, session, professional):
        start, end = _future_iso(hours_from_now=30)
        r = session.post(
            f"{API}/interviews/slots",
            headers=auth_headers(professional["token"]),
            json={
                "start_at": start,
                "end_at": end,
                "skill_set": ["React", "System Design"],
                "experience_years": 4,
                "topic": "TEST_iter9",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("id"), data
        assert data.get("status") in ("available",)


# ------------------- Job Posting mandatory fields -------------------
class TestJobPostingMandatoryFields:
    """POST /api/jobs field guards."""

    def _base_job(self, **overrides):
        payload = {
            "title": "TEST_iter9_job",
            "company": "TEST Co",
            "description": "Looking for engineers.",
            "location": "Bangalore",
            "category": "fresher",
            "experience_required": 0,
            "skills_required": ["Python"],
            "open_positions_label": "1 to 5",
        }
        payload.update(overrides)
        return payload

    def test_missing_title_400(self, session, employer):
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]),
                         json=self._base_job(title=""))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Job Title is required."

    def test_missing_description_400(self, session, employer):
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]),
                         json=self._base_job(description=""))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Job Description is required."

    def test_missing_location_400(self, session, employer):
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]),
                         json=self._base_job(location=""))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Location is required."

    def test_missing_skills_required_400(self, session, employer):
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]),
                         json=self._base_job(skills_required=[]))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Skill Set is required."

    def test_skills_required_only_whitespace_400(self, session, employer):
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]),
                         json=self._base_job(skills_required=["   "]))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Skill Set is required."


# ------------------- open_positions_label -------------------
class TestJobOpenPositionsLabel:
    """Job's open_positions_label is accepted and persisted; default '1 to 5'."""

    def _post_job(self, session, token, **overrides):
        payload = {
            "title": f"TEST_iter9_op_{uuid.uuid4().hex[:6]}",
            "company": "TEST Co",
            "description": "JD",
            "location": "Bangalore",
            "category": "fresher",
            "skills_required": ["Python"],
        }
        payload.update(overrides)
        r = session.post(f"{API}/jobs", headers=auth_headers(token), json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_label_1_to_10_persists(self, session, employer):
        job = self._post_job(session, employer["token"], open_positions_label="1 to 10")
        assert job["open_positions_label"] == "1 to 10"
        assert job["open_positions"] == 10

    def test_label_100_plus_persists(self, session, employer):
        job = self._post_job(session, employer["token"], open_positions_label="100+")
        assert job["open_positions_label"] == "100+"
        # 100+ maps to numeric 100 (server's LABEL_NUMERIC)
        assert job["open_positions"] == 100

    def test_default_label_1_to_5_when_omitted(self, session, employer):
        job = self._post_job(session, employer["token"])
        assert job["open_positions_label"] == "1 to 5"
        assert job["open_positions"] == 5

    def test_label_persisted_on_get_jobs(self, session, employer):
        job = self._post_job(session, employer["token"], open_positions_label="1 to 50")
        # Fetch via list endpoint and assert the same record carries the label
        r = session.get(f"{API}/jobs?limit=100", headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        found = next((j for j in items if j["id"] == job["id"]), None)
        assert found is not None, "Job should be listable after create"
        assert found.get("open_positions_label") == "1 to 50"
        assert found.get("open_positions") == 50


# ------------------- pro missing_fields & auth/me -------------------
class TestProMissingFields:
    """GET /api/auth/me as a pro returns missing_fields[] for 10 mandatory factors."""

    EXPECTED_KEYS = {
        "Full Name", "Mobile Number", "Company Email Address",
        "Alternate Gmail Address", "Company Name", "Designation",
        "Total Experience", "Current Location", "Skill Set", "Profile Photo",
    }

    def test_me_returns_missing_fields_for_raw_pro(self, session):
        # A raw pro (no gmail verify, no profile fields) — should be missing many factors.
        pro = _signup_verify(session, "professional")
        r = session.get(f"{API}/auth/me", headers=auth_headers(pro["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "missing_fields" in body, body
        mf = body["missing_fields"]
        assert isinstance(mf, list)
        # Name is set during signup, email always present. Phone/company/etc are blank → must be missing.
        for key in ["Mobile Number", "Alternate Gmail Address", "Company Name",
                    "Designation", "Total Experience", "Current Location",
                    "Skill Set", "Profile Photo"]:
            assert key in mf, f"Expected '{key}' missing for raw pro; got {mf}"
        # All entries must come from the canonical set
        assert set(mf).issubset(self.EXPECTED_KEYS), f"Unexpected keys: {set(mf) - self.EXPECTED_KEYS}"

    def test_full_profile_clears_missing_fields(self, session, professional):
        # Update profile with all 10 mandatory factors.
        token = professional["token"]
        upd = {
            "name": "Iter9 Pro",
            "phone": "+91 9876543210",
            "company": "Acme",
            "designation": "Senior Engineer",
            "experience_years": 5,
            "current_location": "Bangalore",
            "skills": ["Python", "FastAPI"],
            "expertise": ["Python", "FastAPI"],
            "profile_photo_base64": "data:image/png;base64,iVBORw0KGgo=",
        }
        r = session.put(f"{API}/profile", headers=auth_headers(token), json=upd)
        assert r.status_code == 200, r.text
        # Note: professional fixture already gmail-verified in DB → Alternate Gmail Address satisfied.
        r2 = session.get(f"{API}/auth/me", headers=auth_headers(token))
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["missing_fields"] == [], f"Expected no missing fields, got {body['missing_fields']}"

    def test_alternate_gmail_otp_drops_missing_entry(self, session):
        """Without gmail_verified, 'Alternate Gmail Address' is in missing_fields.
        After /pro/gmail/verify-otp, it disappears."""
        # Use raw pro (NOT the auto-verified fixture)
        pro = _signup_verify(session, "professional")
        r0 = session.get(f"{API}/auth/me", headers=auth_headers(pro["token"]))
        assert r0.status_code == 200
        assert "Alternate Gmail Address" in r0.json()["missing_fields"]

        # Send + verify OTP for an @gmail.com address
        alt = f"test.iter9.{uuid.uuid4().hex[:6]}@gmail.com"
        s = session.post(f"{API}/pro/gmail/send-otp",
                         headers=auth_headers(pro["token"]), json={"email": alt})
        assert s.status_code == 200, s.text
        otp = s.json().get("mock_otp")
        assert otp, "mock_otp must be returned"
        v = session.post(f"{API}/pro/gmail/verify-otp",
                         headers=auth_headers(pro["token"]),
                         json={"email": alt, "otp": otp})
        assert v.status_code == 200, v.text

        r1 = session.get(f"{API}/auth/me", headers=auth_headers(pro["token"]))
        assert r1.status_code == 200, r1.text
        mf = r1.json()["missing_fields"]
        assert "Alternate Gmail Address" not in mf, f"Still missing after verify: {mf}"


# ------------------- Smoke: open_positions backward-compat with numeric only -------------------
class TestJobNumericOpenPositionsBackCompat:
    def test_numeric_open_positions_only_still_works(self, session, employer):
        # Older clients may pass only numeric `open_positions`. Server should accept.
        payload = {
            "title": f"TEST_iter9_legacy_{uuid.uuid4().hex[:6]}",
            "description": "JD",
            "location": "Bangalore",
            "category": "fresher",
            "skills_required": ["Java"],
            "open_positions": 7,
        }
        r = session.post(f"{API}/jobs", headers=auth_headers(employer["token"]), json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["open_positions"] == 7
        # Label falls back to default '1 to 5' when not provided (per server: label = body.open_positions_label or "1 to 5")
        assert data["open_positions_label"] == "1 to 5"
