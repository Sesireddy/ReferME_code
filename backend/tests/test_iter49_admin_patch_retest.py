"""Iter49 retest — verify legacy shadow PATCH handler removal.

Focused on:
- PATCH /api/admin/jobs/{id} with a full walk-in body incl. status='open' → 200 + all fields persist.
- PATCH with status='closed' → 200 + status persisted.
- PATCH with status='draft' → 200 + status persisted.
- PATCH with invalid contact_number → 400.
- PATCH with invalid contact_email → 400.
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from conftest import API, auth_headers


def _future_date(days: int = 15) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(session, admin_token, **overrides):
    payload = {
        "company": "TEST-iter49 Co",
        "title": f"TEST iter49 seed {uuid.uuid4().hex[:6]}",
        "description": "Iter49 retest — full walk-in payload.",
        "location": "Bengaluru",
        "skills_required": ["Comm"],
        "employment_type": "Walk-in Drive",
        "salary_range": "3-5 LPA",
        "open_positions": 2,
        "experience_min": 0,
        "experience_max": 2,
        "walk_in_date": _future_date(7),
        "walk_in_time": "10:00 AM - 4:00 PM",
        "venue": "MG Road",
        "contact_person": "Rita",
        "contact_number": "9876543210",
        "contact_email": "rita@acme.test",
        "application_deadline": _future_date(14),
    }
    payload.update(overrides)
    r = session.post(f"{API}/admin/jobs", json=payload, headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    return r.json()


class TestAdminPatchFull:
    def test_patch_full_walkin_body_all_fields_persist(self, session, admin_token):
        job = _seed(session, admin_token)
        new_title = f"TEST iter49 UPDATED {uuid.uuid4().hex[:5]}"
        body = {
            "status": "open",
            "title": new_title,
            "walk_in_date": _future_date(20),
            "walk_in_time": "9:00 AM",
            "venue": "Whitefield, Bengaluru",
            "contact_email": "hr@iter49.test",
            "skills_required": ["Alpha", "Beta"],
            "experience_min": 2,
            "experience_max": 5,
            "open_positions": 3,
        }
        r = session.patch(f"{API}/admin/jobs/{job['id']}", json=body,
                          headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        got = session.get(f"{API}/jobs/{job['id']}", headers=auth_headers(admin_token)).json()
        assert got["status"] == "open"
        assert got["title"] == new_title
        assert got["walk_in_date"] == body["walk_in_date"]
        assert got["walk_in_time"] == "9:00 AM"
        assert got["venue"] == "Whitefield, Bengaluru"
        assert got["contact_email"] == "hr@iter49.test"
        assert got["skills_required"] == ["Alpha", "Beta"]
        assert got["experience_min"] == 2
        assert got["experience_max"] == 5
        assert got["open_positions"] == 3
        session.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))

    def test_patch_status_closed(self, session, admin_token):
        job = _seed(session, admin_token)
        r = session.patch(f"{API}/admin/jobs/{job['id']}", json={"status": "closed"},
                          headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        got = session.get(f"{API}/jobs/{job['id']}", headers=auth_headers(admin_token)).json()
        assert got["status"] == "closed"
        session.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))

    def test_patch_status_draft(self, session, admin_token):
        job = _seed(session, admin_token)
        r = session.patch(f"{API}/admin/jobs/{job['id']}", json={"status": "draft"},
                          headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        got = session.get(f"{API}/jobs/{job['id']}", headers=auth_headers(admin_token)).json()
        assert got["status"] == "draft"
        session.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))

    def test_patch_invalid_contact_number(self, session, admin_token):
        job = _seed(session, admin_token)
        r = session.patch(f"{API}/admin/jobs/{job['id']}",
                          json={"contact_number": "1234567890"},
                          headers=auth_headers(admin_token))
        assert r.status_code == 400, r.text
        assert "Contact Number" in r.json().get("detail", "")
        session.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))

    def test_patch_invalid_contact_email(self, session, admin_token):
        job = _seed(session, admin_token)
        r = session.patch(f"{API}/admin/jobs/{job['id']}",
                          json={"contact_email": "not-an-email"},
                          headers=auth_headers(admin_token))
        assert r.status_code == 400, r.text
        assert "Contact Email" in r.json().get("detail", "")
        session.delete(f"{API}/admin/jobs/{job['id']}", headers=auth_headers(admin_token))
