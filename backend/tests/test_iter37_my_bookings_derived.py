"""Iteration 37 — /api/interviews/my-bookings derived fields.

Acceptance criteria:
- Response objects include NEW booleans `slot_ended` and `both_joined`.
- Internal `joined_by` array MUST NOT be present in the response.
- slot_ended: end_at past -> True; future -> False.
- both_joined: pro_id AND student_id both in joined_by -> True; otherwise False.
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


def _seed_booked_slot(pro_id, pro_name, student_id, student_name, start_at, end_at, joined_by=None):
    slot_id = uuid.uuid4().hex
    doc = {
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro_id,
        "pro_name": pro_name,
        "start_at": _iso(start_at),
        "end_at": _iso(end_at),
        "scheduled_at": _iso(start_at),
        "skill_set": ["TEST_iter37"],
        "experience_years": 2,
        "topic": "TEST iter37",
        "status": "booked",
        "student_id": student_id,
        "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.example.com/iter37-{slot_id[:8]}",
        "booked_at": _iso(datetime.now(timezone.utc)),
        "created_at": _iso(datetime.now(timezone.utc)),
        "_test_marker": "iter37",
    }
    if joined_by is not None:
        doc["joined_by"] = list(joined_by)
    _mongo().interview_slots.insert_one(doc)
    return slot_id


@pytest.fixture()
def two_users(session, professional, student):
    return professional, student


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _mongo().interview_slots.delete_many({"_test_marker": "iter37"})


class TestMyBookingsDerivedFields:
    """Pro POV /api/interviews/my-bookings returns slot_ended + both_joined, hides joined_by."""

    def test_future_slot_not_ended(self, session, two_users):
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        start = now + timedelta(minutes=5)
        end = now + timedelta(minutes=35)
        sid = _seed_booked_slot(pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"], start, end)

        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(pro["token"]))
        assert r.status_code == 200, r.text
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1, "seeded slot must appear in pro my-bookings"
        item = items[0]
        assert item["slot_ended"] is False, f"future slot must have slot_ended=False, got {item}"
        assert item["both_joined"] is False
        assert "joined_by" not in item, "internal joined_by must be stripped from response"
        # join_enabled: start is in 5 min (within 10-min pre-window) so should be True
        assert item.get("join_enabled") is True

    def test_past_slot_ended_true(self, session, two_users):
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        # end_at must be within last 2 hours otherwise upcoming_only=True filters it out
        start = now - timedelta(minutes=90)
        end = now - timedelta(minutes=60)
        sid = _seed_booked_slot(pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"], start, end)

        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(pro["token"]))
        assert r.status_code == 200
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1
        item = items[0]
        assert item["slot_ended"] is True
        assert item["both_joined"] is False  # no one joined
        assert "joined_by" not in item

    def test_both_joined_true(self, session, two_users):
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=90)
        end = now - timedelta(minutes=60)
        sid = _seed_booked_slot(
            pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"],
            start, end,
            joined_by=[pro["user"]["id"], stu["user"]["id"]],
        )

        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(pro["token"]))
        assert r.status_code == 200
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1
        item = items[0]
        assert item["slot_ended"] is True
        assert item["both_joined"] is True, "both pro+student in joined_by -> both_joined must be True"
        assert "joined_by" not in item

    def test_only_pro_joined_both_joined_false(self, session, two_users):
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=90)
        end = now - timedelta(minutes=60)
        sid = _seed_booked_slot(
            pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"],
            start, end,
            joined_by=[pro["user"]["id"]],  # student missed
        )

        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(pro["token"]))
        assert r.status_code == 200
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1
        item = items[0]
        assert item["slot_ended"] is True
        assert item["both_joined"] is False
        assert "joined_by" not in item

    def test_joined_endpoint_populates_both_joined(self, session, two_users):
        """End-to-end: hit /interviews/{id}/joined as both users, then verify both_joined flips True."""
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        # Use a slot that is CURRENTLY live so /joined is callable (no join window check on /joined,
        # but the slot must exist). end_at slightly past to also exercise slot_ended True afterwards.
        start = now - timedelta(minutes=30)
        end = now + timedelta(minutes=30)  # still live
        sid = _seed_booked_slot(pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"], start, end)

        # Pro joins
        r1 = session.post(f"{API}/interviews/{sid}/joined", headers=auth_headers(pro["token"]))
        assert r1.status_code == 200, r1.text
        # Student joins
        r2 = session.post(f"{API}/interviews/{sid}/joined", headers=auth_headers(stu["token"]))
        assert r2.status_code == 200, r2.text

        # Now back-date end_at to past so slot_ended=True
        _mongo().interview_slots.update_one({"id": sid}, {"$set": {"end_at": _iso(now - timedelta(minutes=10))}})

        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(pro["token"]))
        assert r.status_code == 200
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1
        item = items[0]
        assert item["slot_ended"] is True
        assert item["both_joined"] is True
        assert "joined_by" not in item


class TestStudentMyBookingsAlsoHasDerived:
    """Student POV should also see the derived fields (UI may evolve later) but never joined_by."""

    def test_student_sees_slot_ended_and_no_joined_by(self, session, two_users):
        pro, stu = two_users
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=90)
        end = now - timedelta(minutes=60)
        sid = _seed_booked_slot(
            pro["user"]["id"], pro["user"]["name"], stu["user"]["id"], stu["user"]["name"],
            start, end,
            joined_by=[pro["user"]["id"], stu["user"]["id"]],
        )
        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(stu["token"]))
        assert r.status_code == 200
        items = [x for x in r.json() if x["id"] == sid]
        assert len(items) == 1
        item = items[0]
        assert item["slot_ended"] is True
        assert item["both_joined"] is True
        assert "joined_by" not in item
        # proof_screenshot still hidden from students (iter25 contract preserved)
        assert "proof_screenshot" not in item
