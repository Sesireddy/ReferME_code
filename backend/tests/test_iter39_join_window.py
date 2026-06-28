"""Iteration 39 — Backend join window boundary tests.

Spec: /api/interviews/my-bookings should return join_enabled = TRUE when
  (scheduled_start - 30 min) <= now <= scheduled_end
and FALSE outside this window. Tests 5 boundary scenarios:
  - 35 min before start: FALSE (under OLD 10-min window this would also be FALSE,
    but it's still a valid lower-boundary sanity check)
  - 30 min before start: TRUE (was FALSE under OLD 10-min window — guards regression
    of the window expansion)
  - At start: TRUE
  - At end: TRUE
  - 1 min after end: FALSE
Also asserts ended slots stay in the response (within 2h grace) with
slot_ended=TRUE + join_enabled=FALSE so the frontend can drop them
from the Upcoming tab.
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


def _seed_booked(pro, stu, start_at, end_at):
    sid = uuid.uuid4().hex
    doc = {
        "id": sid,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro["user"]["id"],
        "pro_name": pro["user"]["name"],
        "start_at": _iso(start_at),
        "end_at": _iso(end_at),
        "scheduled_at": _iso(start_at),
        "skill_set": ["TEST_iter39"],
        "experience_years": 2,
        "topic": "TEST iter39",
        "status": "booked",
        "student_id": stu["user"]["id"],
        "student_name": stu["user"]["name"],
        "student_email": f"{stu['user']['name']}@example.com",
        "meeting_url": f"https://meet.example.com/iter39-{sid[:8]}",
        "booked_at": _iso(datetime.now(timezone.utc)),
        "created_at": _iso(datetime.now(timezone.utc)),
        "_test_marker": "iter39",
    }
    _mongo().interview_slots.insert_one(doc)
    return sid


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _mongo().interview_slots.delete_many({"_test_marker": "iter39"})


@pytest.fixture()
def pair(session, professional, student):
    return professional, student


def _fetch_item(session, token, sid):
    r = session.get(
        f"{API}/interviews/my-bookings?upcoming_only=false",
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text
    items = [x for x in r.json() if x["id"] == sid]
    assert len(items) == 1, f"slot {sid} missing"
    return items[0]


class TestJoinWindowBoundaries:
    """5 boundary scenarios for the [start-30min, end] join window."""

    def test_35min_before_start_disabled(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        # start = now + 35 min  -> 30 min before start = now + 5 min, so now < window_start
        start = now + timedelta(minutes=35)
        end = start + timedelta(minutes=30)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["join_enabled"] is False, f"{who['user']['role']} 35min-before should be FALSE"
            assert item["slot_ended"] is False

    def test_30min_before_start_enabled(self, session, pair):
        """KEY regression: under OLD 10-min window this was FALSE; new spec=TRUE."""
        pro, stu = pair
        now = datetime.now(timezone.utc)
        # start exactly 30 min from now -> window_start == now -> enabled
        # Subtract 1s safety so the boundary equality is satisfied even with clock skew.
        start = now + timedelta(minutes=30) - timedelta(seconds=1)
        end = start + timedelta(minutes=30)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["join_enabled"] is True, (
                f"{who['user']['role']} at T-30min boundary should be TRUE "
                f"(this would FAIL under the OLD 10-min window)"
            )
            assert item["slot_ended"] is False

    def test_at_start_enabled(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        start = now - timedelta(seconds=1)  # essentially "at start"
        end = start + timedelta(minutes=30)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["join_enabled"] is True
            assert item["slot_ended"] is False

    def test_at_end_enabled(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        # end ~= now (still <= now)
        start = now - timedelta(minutes=30)
        end = now + timedelta(seconds=1)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["join_enabled"] is True
            assert item["slot_ended"] is False

    def test_1min_after_end_disabled(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=31)
        end = now - timedelta(minutes=1)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["join_enabled"] is False
            assert item["slot_ended"] is True


class TestEndedSlotStillReturned:
    """Past-ended slots within 2h grace must come back with slot_ended=TRUE so
    the UI can decide to drop them from the Upcoming tab. join_enabled=FALSE.
    """

    def test_recently_ended_returns_with_slot_ended_true(self, session, pair):
        pro, stu = pair
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=60)
        end = now - timedelta(minutes=30)
        sid = _seed_booked(pro, stu, start, end)
        for who in (stu, pro):
            item = _fetch_item(session, who["token"], sid)
            assert item["slot_ended"] is True
            assert item["join_enabled"] is False
