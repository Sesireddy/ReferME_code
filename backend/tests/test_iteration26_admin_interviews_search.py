"""Iteration 26 — Admin interviews search must expose completion fields.

Spec covered:
- GET /api/admin/interviews/search must return completed slots with
  proof_screenshot, candidate_rating, candidate_feedback so the Admin → Interviews
  tab can render the lightbox / detail modal.
- Filters (candidate, pro, skill, date, status) still work.
- Auth: non-admin (student / pro) cannot access this endpoint.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from conftest import API, auth_headers


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _now_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_completed_slot(skill="ADMINSEARCH", student_name="TEST stu26", pro_name="TEST pro26"):
    slot_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=40)
    end = now - timedelta(minutes=10)
    db = _mongo()
    db.interview_slots.insert_one({
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": uuid.uuid4().hex,
        "pro_name": pro_name,
        "start_at": _now_iso(start),
        "end_at": _now_iso(end),
        "scheduled_at": _now_iso(start),
        "skill_set": [skill],
        "experience_years": 3,
        "topic": "TEST iter26",
        "status": "completed",
        "student_id": uuid.uuid4().hex,
        "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.example.com/iter26-{slot_id[:8]}",
        "candidate_rating": 8,
        "candidate_feedback": "Strong DSA fundamentals, solid behavioral. Recommend Hire.",
        "proof_screenshot": "data:image/png;base64," + ("A" * 60),
        "completed_at": _now_iso(now),
        "_test_marker": "iter26",
    })
    return slot_id


def _seed_booked_slot(skill="ADMINSEARCH"):
    slot_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=2)
    end = now + timedelta(hours=3)
    db = _mongo()
    db.interview_slots.insert_one({
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": uuid.uuid4().hex,
        "pro_name": "TEST pro26 booked",
        "start_at": _now_iso(start),
        "end_at": _now_iso(end),
        "scheduled_at": _now_iso(start),
        "skill_set": [skill],
        "experience_years": 2,
        "topic": "TEST iter26",
        "status": "booked",
        "student_id": uuid.uuid4().hex,
        "student_name": "TEST stu26 booked",
        "student_email": "stu_b@example.com",
        "meeting_url": f"https://meet.example.com/iter26b-{slot_id[:8]}",
        "_test_marker": "iter26",
    })
    return slot_id


@pytest.fixture(scope="module", autouse=True)
def _cleanup_module():
    yield
    try:
        _mongo().interview_slots.delete_many({"_test_marker": "iter26"})
    except Exception:
        pass


# ----------------------------- tests -----------------------------

class TestAdminInterviewsSearchCompletionFields:
    def test_admin_can_login(self, session):
        r = session.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        assert r.json().get("token")

    def test_completed_slot_returns_proof_rating_feedback(self, session, admin_token):
        slot_id = _seed_completed_slot()
        r = session.get(
            f"{API}/admin/interviews/search?q={slot_id}",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list), rows
        matches = [x for x in rows if x.get("id") == slot_id]
        assert matches, f"seeded completed slot {slot_id} not returned by admin search"
        s = matches[0]
        # Completion fields must be present and exactly the seeded values
        assert s.get("status") == "completed"
        assert s.get("candidate_rating") == 8
        assert s.get("candidate_feedback", "").startswith("Strong DSA")
        assert s.get("proof_screenshot", "").startswith("data:image/png;base64,")
        assert len(s.get("proof_screenshot", "")) >= 20
        # Mongo internal field stripped
        assert "_id" not in s

    def test_filter_by_status_completed(self, session, admin_token):
        slot_id = _seed_completed_slot(skill="ADMINSEARCHFILTERSTATUS")
        r = session.get(
            f"{API}/admin/interviews/search?status=completed&skill=ADMINSEARCHFILTERSTATUS",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert any(x.get("id") == slot_id for x in rows)
        # All rows in the response respect the status filter
        for x in rows:
            assert x.get("status") == "completed"

    def test_filter_by_candidate_name(self, session, admin_token):
        unique = f"UNIQUENAME{uuid.uuid4().hex[:6]}"
        slot_id = _seed_completed_slot(student_name=f"TEST stu26 {unique}")
        r = session.get(
            f"{API}/admin/interviews/search?candidate={unique}",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert any(x.get("id") == slot_id for x in rows), rows

    def test_filter_by_pro_name(self, session, admin_token):
        unique = f"PRO{uuid.uuid4().hex[:6]}"
        slot_id = _seed_completed_slot(pro_name=f"TEST pro26 {unique}")
        r = session.get(
            f"{API}/admin/interviews/search?pro={unique}",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert any(x.get("id") == slot_id for x in rows), rows

    def test_filter_by_skill(self, session, admin_token):
        unique_skill = f"SKILL{uuid.uuid4().hex[:6]}"
        slot_id = _seed_completed_slot(skill=unique_skill)
        r = session.get(
            f"{API}/admin/interviews/search?skill={unique_skill}",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert any(x.get("id") == slot_id for x in rows), rows

    def test_booked_slot_does_not_have_completion_fields(self, session, admin_token):
        slot_id = _seed_booked_slot()
        r = session.get(
            f"{API}/admin/interviews/search?q={slot_id}",
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        matches = [x for x in rows if x.get("id") == slot_id]
        assert matches, rows
        s = matches[0]
        assert s.get("status") == "booked"
        # candidate_rating / proof_screenshot may be absent or None — but not a populated string
        assert not s.get("proof_screenshot"), s.get("proof_screenshot")
        assert s.get("candidate_rating") in (None, 0, ""), s.get("candidate_rating")


class TestAdminInterviewsSearchRBAC:
    def test_non_admin_student_blocked(self, session, student):
        r = session.get(
            f"{API}/admin/interviews/search",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code in (401, 403), r.text

    def test_unauthenticated_blocked(self, session):
        r = session.get(f"{API}/admin/interviews/search")
        assert r.status_code in (401, 403), r.text
