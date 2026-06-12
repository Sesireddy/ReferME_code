"""Iteration 12 — Career Information cascade tests.

Verifies the new conditional completeness rules:
  - preferred_role ∈ {fresher, experienced, intern}.
  - fresher / intern: do NOT require any experienced-only field.
  - experienced: requires company, designation, currently_working,
    working_since_from_*, annual_salary; plus notice_period (when
    currently_working=yes) OR working_since_to_* (when currently_working=no).
  - Partial experienced payload keeps profile_complete=False; full one flips True.
"""
import uuid
import pytest
from conftest import API, auth_headers


_BASE = {
    "name": "Test Student",
    "phone": "+919876543210",
    "gender": "male",
    "dob": "2001-06-15",
    "education": "B.Tech",
    "passed_out_year": 2024,
    "current_location": "Bangalore",
    "skills": ["Python"],
    "resume_link": "https://example.com/cv.pdf",
}


# --- fresher: experienced fields irrelevant ---
class TestFresherCompletes:
    def test_fresher_complete_without_experienced_fields(self, session, student):
        body = {**_BASE, "preferred_role": "fresher", "years_of_experience": 0}
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True

    def test_fresher_complete_even_when_experienced_fields_null(self, session, student):
        # Mirrors frontend save() — explicitly clears experienced fields.
        body = {
            **_BASE,
            "preferred_role": "fresher",
            "years_of_experience": 0,
            "company": None,
            "designation": None,
            "currently_working": None,
            "working_since_from_year": None,
            "working_since_from_month": None,
            "working_since_to_year": None,
            "working_since_to_month": None,
            "notice_period": None,
            "annual_salary": None,
        }
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True


# --- intern: same behaviour as fresher ---
class TestInternCompletes:
    def test_intern_complete_without_experienced_fields(self, session, student):
        body = {**_BASE, "preferred_role": "intern", "years_of_experience": 0}
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True, r.text
        assert r.json()["profile"]["preferred_role"] == "intern"


# --- experienced: full cascade ---
class TestExperiencedCascade:
    def _exp_base(self):
        return {
            **_BASE,
            "preferred_role": "experienced",
            "years_of_experience": 5,
            "company": "Acme",
            "designation": "SDE-2",
            "annual_salary": "6-10",
            "working_since_from_year": "2022",
            "working_since_from_month": "01",
        }

    def test_experienced_partial_payload_incomplete(self, session, student):
        # Missing company / designation / currently_working / annual_salary etc.
        body = {**_BASE, "preferred_role": "experienced", "years_of_experience": 5}
        r = session.put(f"{API}/profile", json=body, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is False

    def test_experienced_currently_working_yes_requires_notice(self, session, student):
        full = {**self._exp_base(), "currently_working": "yes"}
        # Without notice_period -> incomplete
        r = session.put(f"{API}/profile", json=full, headers=auth_headers(student["token"]))
        assert r.json()["user"]["profile_complete"] is False
        # With notice_period -> complete (working_since_to_* not required when working=yes)
        r2 = session.put(f"{API}/profile", json={**full, "notice_period": "1m"}, headers=auth_headers(student["token"]))
        assert r2.json()["user"]["profile_complete"] is True, r2.text

    def test_experienced_currently_working_no_requires_to_dates(self, session, student):
        full_no = {
            **self._exp_base(),
            "currently_working": "no",
            # explicitly clear notice_period (not relevant)
            "notice_period": None,
        }
        r = session.put(f"{API}/profile", json=full_no, headers=auth_headers(student["token"]))
        assert r.json()["user"]["profile_complete"] is False
        # supply only year -> still incomplete (month also required)
        r2 = session.put(
            f"{API}/profile",
            json={**full_no, "working_since_to_year": "2024"},
            headers=auth_headers(student["token"]),
        )
        assert r2.json()["user"]["profile_complete"] is False
        # both year + month -> complete
        r3 = session.put(
            f"{API}/profile",
            json={**full_no, "working_since_to_year": "2024", "working_since_to_month": "06"},
            headers=auth_headers(student["token"]),
        )
        assert r3.json()["user"]["profile_complete"] is True, r3.text

    def test_experienced_notice_period_15d_or_less_accepted(self, session, student):
        # New NOTICE_PERIOD_OPTIONS value
        full = {
            **self._exp_base(),
            "currently_working": "yes",
            "notice_period": "15d_or_less",
        }
        r = session.put(f"{API}/profile", json=full, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["user"]["profile_complete"] is True

    def test_experienced_then_switch_to_fresher_clears_completion_path(self, session, student):
        # Mark experienced fully -> complete
        full = {**self._exp_base(), "currently_working": "yes", "notice_period": "1m"}
        r = session.put(f"{API}/profile", json=full, headers=auth_headers(student["token"]))
        assert r.json()["user"]["profile_complete"] is True
        # Switch to fresher; frontend explicitly nulls experienced fields on save()
        flip = {
            **_BASE,
            "preferred_role": "fresher",
            "years_of_experience": 0,
            "company": None,
            "designation": None,
            "currently_working": None,
            "working_since_from_year": None,
            "working_since_from_month": None,
            "working_since_to_year": None,
            "working_since_to_month": None,
            "notice_period": None,
            "annual_salary": None,
        }
        r2 = session.put(f"{API}/profile", json=flip, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json()["user"]["profile_complete"] is True
        assert r2.json()["profile"]["preferred_role"] == "fresher"
        # And experienced fields are now null
        for k in ("company", "designation", "currently_working", "notice_period",
                  "annual_salary", "working_since_from_year"):
            assert r2.json()["profile"].get(k) in (None, "", []), (k, r2.json()["profile"].get(k))
