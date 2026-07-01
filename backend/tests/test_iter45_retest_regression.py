"""Iter45 retest regression smoke — confirm /api/jobs still excludes admin for students,
?source=professional works, and admin flow untouched."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from conftest import API, auth_headers, _signup_verify


def _future_date(days: int = 10) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _base_admin_payload(**overrides):
    body = {
        "company": "TEST Regression Co",
        "title": f"TEST-reg-{uuid.uuid4().hex[:5]}",
        "description": "Reg smoke test admin job.",
        "location": "Bengaluru",
        "skills_required": ["Communication"],
        "employment_type": "Walk-in Drive",
        "salary_range": "3-5 LPA",
        "open_positions": 1,
        "experience_min": 0,
        "experience_max": 2,
        "walk_in_date": _future_date(7),
        "walk_in_time": "10:00 AM - 4:00 PM",
        "venue": "MG Road",
        "contact_person": "Rita",
        "contact_number": "9876543210",
        "contact_email": "rita@reg.test",
        "application_deadline": _future_date(14),
    }
    body.update(overrides)
    return body


class TestRegressionSmoke:
    """Regression smoke — student list + source filters + admin post."""

    @pytest.fixture(scope="class")
    def admin_token(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        r = s.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
        assert r.status_code == 200
        return r.json()["token"]

    @pytest.fixture(scope="class")
    def seeded_admin_job(self, admin_token, request):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        r = s.post(f"{API}/admin/jobs", json=_base_admin_payload(), headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        job = r.json()

        def _cleanup():
            s.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))
        request.addfinalizer(_cleanup)
        return job

    def test_admin_can_post_job(self, admin_token, seeded_admin_job):
        # Fixture success == POST /admin/jobs works
        assert seeded_admin_job["source"] == "admin"
        assert seeded_admin_job["status"] == "open"
        assert seeded_admin_job["verification_status"] == "verified"

    def test_student_jobs_excludes_admin_source(self, session, seeded_admin_job):
        stud = _signup_verify(session, "student", prefix="RegStud")
        r = session.get(f"{API}/jobs", headers=auth_headers(stud["token"]))
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        admin_hits = [j for j in items if j.get("source") == "admin"]
        assert admin_hits == [], f"Expected no admin jobs in default student /jobs, got {len(admin_hits)}"

    def test_student_source_professional_excludes_admin(self, session, seeded_admin_job):
        stud = _signup_verify(session, "student", prefix="RegStud")
        r = session.get(f"{API}/jobs?source=professional", headers=auth_headers(stud["token"]))
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        for j in items:
            assert j.get("source") != "admin"

    def test_student_source_admin_returns_admin_only(self, session, seeded_admin_job):
        stud = _signup_verify(session, "student", prefix="RegStud")
        r = session.get(f"{API}/jobs?source=admin", headers=auth_headers(stud["token"]))
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        ids = [j["id"] for j in items]
        assert seeded_admin_job["id"] in ids
        for j in items:
            assert j.get("source") == "admin"
            assert j.get("status") == "open"
