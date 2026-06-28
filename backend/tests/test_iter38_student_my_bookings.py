"""Iteration 38 — Student counterpart of iter37 pro-side fix.

Validates that GET /api/interviews/my-bookings (student POV) returns the four
spec scenarios with the right combination of (status, slot_ended, both_joined,
feedback, candidate_rating) so the frontend can split the list into:
  - Upcoming tab: status booked/upcoming AND not slot_ended
  - Completed tab: status==completed OR (status booked/upcoming AND slot_ended)
And that `joined_by` is stripped + `slot_ended`/`both_joined` are present on
every record.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient

from conftest import API, auth_headers


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_slot(*, pro_id, pro_name, student_id, student_name, start_at, end_at,
               status="booked", joined_by=None, feedback=None, candidate_rating=None):
    slot_id = uuid.uuid4().hex
    doc = {
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro_id,
        "pro_name": pro_name,
        "start_at": _iso(start_at),
        "end_at": _iso(end_at),
        "scheduled_at": _iso(start_at),
        "skill_set": ["TEST_iter38"],
        "experience_years": 2,
        "topic": "TEST iter38",
        "status": status,
        "student_id": student_id,
        "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.example.com/iter38-{slot_id[:8]}",
        "booked_at": _iso(datetime.now(timezone.utc)),
        "created_at": _iso(datetime.now(timezone.utc)),
        "_test_marker": "iter38",
    }
    if joined_by is not None:
        doc["joined_by"] = list(joined_by)
    if feedback is not None:
        doc["feedback"] = feedback
    if candidate_rating is not None:
        doc["candidate_rating"] = candidate_rating
    _mongo().interview_slots.insert_one(doc)
    return slot_id


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _mongo().interview_slots.delete_many({"_test_marker": "iter38"})


@pytest.fixture()
def pair(session, professional, student):
    return professional, student


class TestStudentMyBookingsScenarios:
    """4 spec scenarios that the student UI splits across Upcoming/Completed."""

    def _fetch(self, session, stu, sid):
        r = session.get(f"{API}/interviews/my-bookings?upcoming_only=false",
                        headers=auth_headers(stu["token"]))
        assert r.status_code == 200, r.text
        matches = [x for x in r.json() if x["id"] == sid]
        assert len(matches) == 1, f"slot {sid} missing in student my-bookings"
        return matches[0]

    def test_scenario_a_future_active(self, session, pair):
        """A: future slot, booked, no joins yet → upcoming tab."""
        pro, stu = pair
        now = datetime.now(timezone.utc)
        sid = _seed_slot(
            pro_id=pro["user"]["id"], pro_name=pro["user"]["name"],
            student_id=stu["user"]["id"], student_name=stu["user"]["name"],
            start_at=now + timedelta(hours=2), end_at=now + timedelta(hours=2, minutes=30),
            status="booked",
        )
        item = self._fetch(session, stu, sid)
        assert item["status"] == "booked"
        assert item["slot_ended"] is False
        assert item["both_joined"] is False
        assert "joined_by" not in item

    def test_scenario_b_completed_with_feedback(self, session, pair):
        """B: past slot, status=completed, both_joined=true, feedback + rating present."""
        pro, stu = pair
        now = datetime.now(timezone.utc)
        sid = _seed_slot(
            pro_id=pro["user"]["id"], pro_name=pro["user"]["name"],
            student_id=stu["user"]["id"], student_name=stu["user"]["name"],
            start_at=now - timedelta(hours=2), end_at=now - timedelta(hours=1, minutes=30),
            status="completed",
            joined_by=[pro["user"]["id"], stu["user"]["id"]],
            feedback="Strong fundamentals across DSA, clear communication, work on system-design depth.",
            candidate_rating=8,
        )
        item = self._fetch(session, stu, sid)
        assert item["status"] == "completed"
        assert item["slot_ended"] is True
        assert item["both_joined"] is True
        assert item.get("feedback")
        assert item.get("candidate_rating") == 8
        assert "joined_by" not in item

    def test_scenario_c_past_booked_both_joined(self, session, pair):
        """C: past slot, status=booked (pro forgot), both joined."""
        pro, stu = pair
        now = datetime.now(timezone.utc)
        sid = _seed_slot(
            pro_id=pro["user"]["id"], pro_name=pro["user"]["name"],
            student_id=stu["user"]["id"], student_name=stu["user"]["name"],
            start_at=now - timedelta(minutes=90), end_at=now - timedelta(minutes=60),
            status="booked",
            joined_by=[pro["user"]["id"], stu["user"]["id"]],
        )
        item = self._fetch(session, stu, sid)
        assert item["status"] == "booked"
        assert item["slot_ended"] is True
        assert item["both_joined"] is True
        assert not item.get("feedback")
        assert "joined_by" not in item

    def test_scenario_d_no_show(self, session, pair):
        """D: past slot, status=booked, joined_by=[pro] only → student no-show."""
        pro, stu = pair
        now = datetime.now(timezone.utc)
        sid = _seed_slot(
            pro_id=pro["user"]["id"], pro_name=pro["user"]["name"],
            student_id=stu["user"]["id"], student_name=stu["user"]["name"],
            start_at=now - timedelta(minutes=90), end_at=now - timedelta(minutes=60),
            status="booked",
            joined_by=[pro["user"]["id"]],
        )
        item = self._fetch(session, stu, sid)
        assert item["status"] == "booked"
        assert item["slot_ended"] is True
        assert item["both_joined"] is False
        assert "joined_by" not in item


class TestStudentMyBookingsContract:
    def test_joined_by_never_in_response(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        sid = _seed_slot(
            pro_id=pro["user"]["id"], pro_name=pro["user"]["name"],
            student_id=stu["user"]["id"], student_name=stu["user"]["name"],
            start_at=now - timedelta(minutes=90), end_at=now - timedelta(minutes=60),
            status="completed",
            joined_by=[pro["user"]["id"], stu["user"]["id"]],
            feedback="ok feedback line that is reasonably long for spec.",
            candidate_rating=7,
        )
        r = session.get(f"{API}/interviews/my-bookings?upcoming_only=false",
                        headers=auth_headers(stu["token"]))
        assert r.status_code == 200
        for item in r.json():
            assert "joined_by" not in item, "internal joined_by must be stripped"
            assert "slot_ended" in item
            assert "both_joined" in item
        # Spot the seeded one
        assert any(x["id"] == sid for x in r.json())
