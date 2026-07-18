"""Iter 69 — Join Meeting 10-minute window enforcement.

Covers:
- GET /api/interviews/my-bookings — join_enabled + meeting_url redaction.
- POST /api/interviews/{slot_id}/joined — window enforcement (403 before/after, 200 within),
  and non-participant rejection.

Seeds slots directly into `db.interview_slots` with the desired start_at/end_at.
"""
import os
import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "Backend URL missing from env"

MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ["DB_NAME"].strip('"')


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id() -> str:
    import uuid
    return str(uuid.uuid4())


# ------------------------ Fixtures ------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _signup_and_verify(api: requests.Session, email: str, password: str, role: str, name: str) -> dict:
    r = api.post(f"{BASE_URL}/api/auth/signup", json={
        "email": email, "password": password, "role": role, "name": name,
    })
    assert r.status_code == 200, f"signup failed {r.status_code} {r.text}"
    body = r.json()
    otp = body.get("mock_otp")
    assert otp, f"mock_otp missing: {body}"
    r2 = api.post(f"{BASE_URL}/api/auth/verify-otp", json={
        "email": email, "otp": otp, "purpose": "verify_email",
    })
    assert r2.status_code == 200, f"verify-otp failed {r2.status_code} {r2.text}"
    data = r2.json()
    return {"token": data["token"], "user": data["user"], "email": email}


@pytest.fixture(scope="module")
def actors(api):
    ts = int(time.time())
    pro = _signup_and_verify(api, f"iter69_pro_{ts}@acmecorp.io", "Passw0rd!", "professional", "Iter69 Pro")
    student = _signup_and_verify(api, f"iter69_stu_{ts}@example.com", "Passw0rd!", "student", "Iter69 Student")
    other = _signup_and_verify(api, f"iter69_other_{ts}@example.com", "Passw0rd!", "student", "Iter69 Other")
    return {"pro": pro, "student": student, "other": other}


def _seed_slot(mongo, pro_id, student_id, start_at, end_at, slot_id=None):
    slot_id = slot_id or new_id()
    doc = {
        "id": slot_id,
        "session_id": new_id(),
        "pro_id": pro_id,
        "pro_name": "Iter69 Pro",
        "start_at": iso(start_at),
        "end_at": iso(end_at),
        "scheduled_at": iso(start_at),
        "skill_set": ["python"],
        "experience_years": 0,
        "topic": "Iter69 test",
        "status": "booked",
        "student_id": student_id,
        "student_name": "Iter69 Student",
        "student_email": "iter69_stu@example.com",
        "meeting_url": f"https://meet.jit.si/ReferME-iter69-{slot_id[:8]}",
        "created_at": iso(datetime.now(timezone.utc)),
        "booked_at": iso(datetime.now(timezone.utc)),
        "credits_charged": 0,
    }
    asyncio.get_event_loop().run_until_complete(mongo.interview_slots.insert_one(doc))
    return doc


@pytest.fixture(scope="module")
def slots(mongo, actors):
    pro_id = actors["pro"]["user"]["id"]
    student_id = actors["student"]["user"]["id"]
    now = datetime.now(timezone.utc)
    seeded = {
        # 1) Starts in 30 min (outside window)
        "future_30m": _seed_slot(mongo, pro_id, student_id, now + timedelta(minutes=30), now + timedelta(minutes=60)),
        # 2) Starts in 5 min (inside window)
        "soon_5m": _seed_slot(mongo, pro_id, student_id, now + timedelta(minutes=5), now + timedelta(minutes=35)),
        # 3) Starts in exactly 10 min (edge — window opens now)
        "edge_10m": _seed_slot(mongo, pro_id, student_id, now + timedelta(minutes=10), now + timedelta(minutes=40)),
        # 4) In progress (started 5 min ago, ends in 20 min)
        "in_progress": _seed_slot(mongo, pro_id, student_id, now - timedelta(minutes=5), now + timedelta(minutes=20)),
        # 5) Ended 5 min ago
        "ended": _seed_slot(mongo, pro_id, student_id, now - timedelta(minutes=35), now - timedelta(minutes=5)),
    }
    yield seeded
    # Cleanup
    ids = [s["id"] for s in seeded.values()]
    asyncio.get_event_loop().run_until_complete(mongo.interview_slots.delete_many({"id": {"$in": ids}}))
    asyncio.get_event_loop().run_until_complete(mongo.users.delete_many({"id": {"$in": [
        actors["pro"]["user"]["id"], actors["student"]["user"]["id"], actors["other"]["user"]["id"]
    ]}}))


def _auth_hdr(actor):
    return {"Authorization": f"Bearer {actor['token']}"}


# ------------------------ Tests ------------------------
class TestMyBookingsJoinWindow:
    """GET /api/interviews/my-bookings — join_enabled + meeting_url redaction."""

    def test_bookings_include_join_flags(self, api, actors, slots):
        r = api.get(f"{BASE_URL}/api/interviews/my-bookings", headers=_auth_hdr(actors["student"]))
        assert r.status_code == 200, r.text
        by_id = {b["id"]: b for b in r.json()}

        # 1) 30-min-away slot → join_enabled False, meeting_url hidden
        b30 = by_id[slots["future_30m"]["id"]]
        assert b30["join_enabled"] is False, b30
        assert b30.get("meeting_url_hidden") is True
        assert "meeting_url" not in b30 or not b30.get("meeting_url")

        # 2) 5-min slot → join_enabled True, meeting_url visible
        b5 = by_id[slots["soon_5m"]["id"]]
        assert b5["join_enabled"] is True, b5
        assert b5.get("meeting_url"), "meeting_url should be visible when join_enabled=true"
        assert not b5.get("meeting_url_hidden"), b5

        # 3) Exactly 10-min → join_enabled True (edge)
        b10 = by_id[slots["edge_10m"]["id"]]
        assert b10["join_enabled"] is True, b10
        assert b10.get("meeting_url")

        # 4) In-progress → join_enabled True
        bip = by_id[slots["in_progress"]["id"]]
        assert bip["join_enabled"] is True, bip
        assert bip.get("meeting_url")

        # 5) Ended 5 min ago → join_enabled False, url hidden
        bend = by_id[slots["ended"]["id"]]
        assert bend["join_enabled"] is False, bend
        assert bend.get("meeting_url_hidden") is True
        assert "meeting_url" not in bend or not bend.get("meeting_url")


class TestJoinedEndpoint:
    """POST /api/interviews/{slot_id}/joined — window + participant enforcement."""

    def test_before_window_returns_403_not_available(self, api, actors, slots):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['future_30m']['id']}/joined",
            headers=_auth_hdr(actors["student"]),
        )
        assert r.status_code == 403, r.text
        assert "10 minutes before" in r.json().get("detail", ""), r.json()

    def test_inside_window_5m_returns_200(self, api, actors, slots, mongo):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['soon_5m']['id']}/joined",
            headers=_auth_hdr(actors["student"]),
        )
        assert r.status_code == 200, r.text
        # Verify persistence: joined_by contains the student id
        student_id = actors["student"]["user"]["id"]
        slot_doc = asyncio.get_event_loop().run_until_complete(
            mongo.interview_slots.find_one({"id": slots["soon_5m"]["id"]}, {"_id": 0, "joined_by": 1})
        )
        assert student_id in (slot_doc.get("joined_by") or [])

    def test_edge_10m_returns_200(self, api, actors, slots):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['edge_10m']['id']}/joined",
            headers=_auth_hdr(actors["student"]),
        )
        assert r.status_code == 200, r.text

    def test_in_progress_pro_can_join(self, api, actors, slots):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['in_progress']['id']}/joined",
            headers=_auth_hdr(actors["pro"]),
        )
        assert r.status_code == 200, r.text

    def test_ended_slot_returns_403_session_ended(self, api, actors, slots):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['ended']['id']}/joined",
            headers=_auth_hdr(actors["student"]),
        )
        assert r.status_code == 403, r.text
        assert "session has ended" in r.json().get("detail", ""), r.json()

    def test_non_participant_returns_403_not_your_session(self, api, actors, slots):
        r = api.post(
            f"{BASE_URL}/api/interviews/{slots['soon_5m']['id']}/joined",
            headers=_auth_hdr(actors["other"]),
        )
        assert r.status_code == 403, r.text
        assert "Not your session" in r.json().get("detail", ""), r.json()
