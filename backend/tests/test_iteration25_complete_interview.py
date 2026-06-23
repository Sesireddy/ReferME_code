"""Iteration 25 — Mock Interview Completion enhancement.

Spec covered:
- Mandatory feedback (>=20 chars) and proof_screenshot (>=20 chars) — Pydantic 422.
- Scheduled start time has passed gate (no join-required, no 15-min minimum).
- +35 credits awarded ONLY when rating + feedback + proof all valid.
- /interviews/my-bookings hides proof_screenshot for students; visible for pros.
- Student TPS / pro rating aggregation still works.
"""
import os
import uuid
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from conftest import API, auth_headers, _gmail_verify_in_db


# ----------------------------- helpers -----------------------------

def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _now_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_booked_slot(pro_id: str, pro_name: str, student_id: str, student_name: str,
                     start_at: datetime, end_at: datetime) -> str:
    slot_id = uuid.uuid4().hex
    db = _mongo()
    db.interview_slots.insert_one({
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro_id,
        "pro_name": pro_name,
        "start_at": _now_iso(start_at),
        "end_at": _now_iso(end_at),
        "scheduled_at": _now_iso(start_at),
        "skill_set": ["TEST"],
        "experience_years": 2,
        "topic": "TEST Iteration 25",
        "status": "booked",
        "student_id": student_id,
        "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.example.com/test-{slot_id[:8]}",
        "booked_at": _now_iso(datetime.now(timezone.utc)),
        "created_at": _now_iso(datetime.now(timezone.utc)),
        "_test_marker": "iter25",
    })
    return slot_id


@pytest.fixture()
def seeded_slot_past(professional, student):
    """A booked slot whose start_at is in the past — completable."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5)
    end = now + timedelta(minutes=25)
    slot_id = _seed_booked_slot(
        professional["user"]["id"], professional["user"].get("name", "pro"),
        student["user"]["id"], student["user"].get("name", "stu"),
        start, end,
    )
    yield slot_id
    # Cleanup
    try:
        _mongo().interview_slots.delete_one({"id": slot_id})
    except Exception:
        pass


@pytest.fixture()
def seeded_slot_future(professional, student):
    """A booked slot whose start_at is still in the future."""
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=20)
    end = now + timedelta(minutes=50)
    slot_id = _seed_booked_slot(
        professional["user"]["id"], professional["user"].get("name", "pro"),
        student["user"]["id"], student["user"].get("name", "stu"),
        start, end,
    )
    yield slot_id
    try:
        _mongo().interview_slots.delete_one({"id": slot_id})
    except Exception:
        pass


VALID_FEEDBACK = "Great communication and solid problem solving. Recommend hire."  # >=20 chars
VALID_PROOF = "data:image/png;base64," + ("A" * 40)  # >=20 chars


# ----------------------------- validation tests -----------------------------

class TestCompleteValidation:
    def test_no_feedback_rejected_422(self, session, professional, seeded_slot_past):
        r = session.post(
            f"{API}/interviews/{seeded_slot_past}/complete",
            json={"rating": 8, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code in (400, 422), r.text

    def test_short_feedback_rejected(self, session, professional, seeded_slot_past):
        r = session.post(
            f"{API}/interviews/{seeded_slot_past}/complete",
            json={"rating": 8, "feedback": "too short", "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code in (400, 422), r.text

    def test_no_proof_rejected_422(self, session, professional, seeded_slot_past):
        r = session.post(
            f"{API}/interviews/{seeded_slot_past}/complete",
            json={"rating": 8, "feedback": VALID_FEEDBACK},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code in (400, 422), r.text

    def test_short_proof_rejected(self, session, professional, seeded_slot_past):
        r = session.post(
            f"{API}/interviews/{seeded_slot_past}/complete",
            json={"rating": 8, "feedback": VALID_FEEDBACK, "proof_screenshot": "tiny"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code in (400, 422), r.text

    def test_complete_before_start_blocked(self, session, professional, seeded_slot_future):
        r = session.post(
            f"{API}/interviews/{seeded_slot_future}/complete",
            json={"rating": 9, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 400, r.text
        assert "before the scheduled start time" in (r.json().get("detail") or "").lower() or \
               "scheduled start time" in (r.json().get("detail") or "")


# ----------------------------- happy path + side effects -----------------------------

class TestCompleteHappyPath:
    def test_complete_awards_credits_persists_proof_and_visibility(
        self, session, professional, student, seeded_slot_past,
    ):
        # Snapshot pro credits before
        before = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
        assert before.status_code == 200
        credits_before = int((before.json().get("user") or {}).get("credits") or 0)

        # Complete
        r = session.post(
            f"{API}/interviews/{seeded_slot_past}/complete",
            json={"rating": 9, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("earned") == 35
        assert data.get("candidate_rating") == 9
        assert isinstance(data.get("pro_rating"), (int, float))

        # Credits +35
        after = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
        credits_after = int((after.json().get("user") or {}).get("credits") or 0)
        assert credits_after - credits_before == 35, f"expected +35, got {credits_after - credits_before}"

        # Mongo verifies slot completion & proof persisted
        slot = _mongo().interview_slots.find_one({"id": seeded_slot_past}, {"_id": 0})
        assert slot["status"] == "completed"
        assert slot.get("proof_screenshot") == VALID_PROOF
        assert slot.get("candidate_feedback", "").startswith(VALID_FEEDBACK[:20])
        assert slot.get("candidate_rating") == 9

        # /my-bookings as STUDENT — proof_screenshot must NOT appear
        stu = session.get(
            f"{API}/interviews/my-bookings?upcoming_only=false",
            headers=auth_headers(student["token"]),
        )
        assert stu.status_code == 200, stu.text
        rows = stu.json()
        target_rows = [s for s in rows if s.get("id") == seeded_slot_past]
        assert target_rows, "completed slot must appear in student my-bookings"
        for row in target_rows:
            assert "proof_screenshot" not in row, \
                f"proof_screenshot leaked to student: {list(row.keys())}"

        # /my-bookings as PROFESSIONAL — proof_screenshot MUST appear
        pro = session.get(
            f"{API}/interviews/my-bookings?upcoming_only=false",
            headers=auth_headers(professional["token"]),
        )
        assert pro.status_code == 200, pro.text
        prows = [s for s in pro.json() if s.get("id") == seeded_slot_past]
        assert prows, "completed slot must appear in pro my-bookings"
        assert prows[0].get("proof_screenshot") == VALID_PROOF

    def test_aggregations_after_complete(self, session, professional, student):
        """After completion the pro rating count should increment and student
        interviews_attended/student_rating should refresh."""
        # Snapshot pro
        db = _mongo()
        pro_before = db.users.find_one({"id": professional["user"]["id"]}, {"_id": 0})
        pro_rc_before = int(pro_before.get("ratings_count") or 0)
        pro_ic_before = int(pro_before.get("interviews_conducted") or 0)
        stu_before = db.users.find_one({"id": student["user"]["id"]}, {"_id": 0})
        stu_ia_before = int(stu_before.get("interviews_attended") or 0)

        # Seed + complete a slot (inline because we need fresh state vs other test)
        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], professional["user"].get("name", "pro"),
            student["user"]["id"], student["user"].get("name", "stu"),
            now - timedelta(minutes=2), now + timedelta(minutes=28),
        )
        try:
            r = session.post(
                f"{API}/interviews/{slot_id}/complete",
                json={"rating": 7, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
                headers=auth_headers(professional["token"]),
            )
            assert r.status_code == 200, r.text

            # Re-read user docs
            pro_after = db.users.find_one({"id": professional["user"]["id"]}, {"_id": 0})
            stu_after = db.users.find_one({"id": student["user"]["id"]}, {"_id": 0})
            assert int(pro_after.get("ratings_count") or 0) == pro_rc_before + 1
            assert int(pro_after.get("interviews_conducted") or 0) == pro_ic_before + 1
            assert int(stu_after.get("interviews_attended") or 0) == stu_ia_before + 1
            assert float(stu_after.get("student_rating") or 0) > 0
        finally:
            db.interview_slots.delete_one({"id": slot_id})


# ----------------------------- RBAC -----------------------------

class TestCompleteRBAC:
    def test_student_cannot_complete(self, session, student, professional):
        """Only the owning pro can call /complete."""
        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], "p", student["user"]["id"], "s",
            now - timedelta(minutes=5), now + timedelta(minutes=25),
        )
        try:
            r = session.post(
                f"{API}/interviews/{slot_id}/complete",
                json={"rating": 8, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
                headers=auth_headers(student["token"]),
            )
            assert r.status_code in (401, 403), r.text
        finally:
            _mongo().interview_slots.delete_one({"id": slot_id})

    def test_other_pro_cannot_complete(self, session, professional, student):
        """A different pro hitting /complete should 404 (ownership check)."""
        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], "p", student["user"]["id"], "s",
            now - timedelta(minutes=5), now + timedelta(minutes=25),
        )
        # Create a second pro
        other_email = f"test_pro_other_{uuid.uuid4().hex[:8]}@referme.io"
        password = "Test@12345"
        s1 = session.post(f"{API}/auth/signup", json={
            "email": other_email, "password": password, "role": "professional", "name": "Other"
        })
        assert s1.status_code == 200, s1.text
        otp = s1.json()["mock_otp"]
        s2 = session.post(f"{API}/auth/verify-otp", json={
            "email": other_email, "otp": otp, "purpose": "verify_email"
        })
        assert s2.status_code == 200
        other_token = s2.json()["token"]
        try:
            r = session.post(
                f"{API}/interviews/{slot_id}/complete",
                json={"rating": 8, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
                headers=auth_headers(other_token),
            )
            assert r.status_code == 404, r.text
        finally:
            _mongo().interview_slots.delete_one({"id": slot_id})
            _mongo().users.delete_one({"email": other_email})
