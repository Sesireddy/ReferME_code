"""Iteration 34 — Working Professional's "Your slots" filter.

Spec covered:
- GET /api/interviews/slots as professional (no pro_id) must HIDE:
  * status='available' AND end_at <= now (expired awaiting-booking slots)
  * status in {'completed','cancelled'}
- GET /api/interviews/slots as professional must KEEP:
  * status='booked' (regardless of time, until pro marks Done)
  * status='available' AND end_at > now (still bookable)
- After POST /interviews/{slot_id}/complete the slot must NOT appear in /interviews/slots for the pro.
- After completion, /interviews/my-bookings?upcoming_only=false MUST still include it.
- Student-facing /api/interviews/slots (no pro_id) unchanged: only available + future.
- Student drill-down /api/interviews/slots?pro_id=<pro> still works: available + booked, hide cancelled/expired.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from conftest import API, auth_headers, _gmail_verify_in_db


# ---------------------- helpers ----------------------

def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mark_phone_verified(user_id: str, phone: str = "+919800099001"):
    _mongo().users.update_one(
        {"id": user_id},
        {"$set": {"profile.phone": phone, "profile.phone_verified": True}},
    )


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


VALID_FEEDBACK = "Great communication and solid problem solving. Recommend hire."
VALID_PROOF = "data:image/png;base64," + ("A" * 40)


@pytest.fixture()
def pro_with_three_slots(session, professional, student):
    """Seed scenario:
      A) tomorrow 11:00-11:30 → available, future (must stay)
      B) 1h ago → 30 min ago → available, past (must be hidden)
      C) tomorrow 12:00-12:30 → student books → booked (must stay)
    Returns (pro, student, slot_a_id, slot_b_id, slot_c_id).
    """
    db = _mongo()
    now = datetime.now(timezone.utc)
    pro_id = professional["user"]["id"]
    pro_name = professional["user"].get("name") or "pro"
    # Phone-gate bypass: required before posting slots (require_phone_verified).
    _mark_phone_verified(pro_id)

    # --- Slot A: future, available ---
    start_a = (now + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    end_a = start_a + timedelta(minutes=30)
    r = session.post(
        f"{API}/interviews/slots",
        json={
            "start_at": _iso(start_a),
            "end_at": _iso(end_a),
            "skill_set": ["TEST_ITER34"],
            "experience_years": 2,
            "topic": "TEST iter34 A future",
        },
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 200, r.text
    slot_a_id = r.json()["id"]

    # --- Slot C: future, will be booked ---
    start_c = (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    end_c = start_c + timedelta(minutes=30)
    r = session.post(
        f"{API}/interviews/slots",
        json={
            "start_at": _iso(start_c),
            "end_at": _iso(end_c),
            "skill_set": ["TEST_ITER34"],
            "experience_years": 2,
            "topic": "TEST iter34 C booked",
        },
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 200, r.text
    slot_c_id = r.json()["id"]

    # Student books C
    rb = session.post(
        f"{API}/interviews/book",
        json={"slot_id": slot_c_id},
        headers=auth_headers(student["token"]),
    )
    assert rb.status_code == 200, rb.text

    # --- Slot B: insert directly (create endpoint blocks past timestamps) ---
    slot_b_id = uuid.uuid4().hex
    past_start = now - timedelta(hours=1)
    past_end = now - timedelta(minutes=30)
    db.interview_slots.insert_one({
        "id": slot_b_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro_id,
        "pro_name": pro_name,
        "start_at": _iso(past_start),
        "end_at": _iso(past_end),
        "scheduled_at": _iso(past_start),
        "skill_set": ["TEST_ITER34"],
        "experience_years": 2,
        "topic": "TEST iter34 B expired",
        "status": "available",
        "student_id": None,
        "student_name": None,
        "meeting_url": f"https://meet.example.com/test-{slot_b_id[:8]}",
        "created_at": _iso(now),
        "_test_marker": "iter34",
    })

    yield {
        "pro": professional,
        "student": student,
        "slot_a": slot_a_id,
        "slot_b": slot_b_id,
        "slot_c": slot_c_id,
    }

    # Cleanup all three
    for sid in (slot_a_id, slot_b_id, slot_c_id):
        try:
            db.interview_slots.delete_one({"id": sid})
        except Exception:
            pass
    try:
        db.interview_bookings.delete_many({"slot_id": {"$in": [slot_a_id, slot_b_id, slot_c_id]}})
    except Exception:
        pass


# ---------------------- core filter tests ----------------------

class TestYourSlotsFilter:
    def test_pro_your_slots_hides_expired_available(self, session, pro_with_three_slots):
        ctx = pro_with_three_slots
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(ctx["pro"]["token"]))
        assert r.status_code == 200, r.text
        ids = [s["id"] for s in r.json()]
        assert ctx["slot_a"] in ids, "future available slot A must be returned"
        assert ctx["slot_c"] in ids, "booked slot C must be returned"
        assert ctx["slot_b"] not in ids, "expired available slot B must be hidden"

    def test_pro_your_slots_keeps_booked(self, session, pro_with_three_slots):
        ctx = pro_with_three_slots
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(ctx["pro"]["token"]))
        assert r.status_code == 200
        c_row = next((s for s in r.json() if s["id"] == ctx["slot_c"]), None)
        assert c_row is not None
        assert c_row.get("status") == "booked"

    def test_pro_your_slots_keeps_future_available(self, session, pro_with_three_slots):
        ctx = pro_with_three_slots
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(ctx["pro"]["token"]))
        assert r.status_code == 200
        a_row = next((s for s in r.json() if s["id"] == ctx["slot_a"]), None)
        assert a_row is not None
        assert a_row.get("status") == "available"


# ---------------------- completed slot transitions out ----------------------

class TestCompletedSlotTransition:
    def test_completed_slot_disappears_from_your_slots_but_remains_in_my_bookings(
        self, session, pro_with_three_slots,
    ):
        ctx = pro_with_three_slots
        pro_token = ctx["pro"]["token"]

        # Make slot C completable: push start_at into the past via DB
        db = _mongo()
        now = datetime.now(timezone.utc)
        db.interview_slots.update_one(
            {"id": ctx["slot_c"]},
            {"$set": {
                "start_at": _iso(now - timedelta(minutes=5)),
                "end_at": _iso(now + timedelta(minutes=25)),
            }},
        )

        # Pro completes C
        r = session.post(
            f"{API}/interviews/{ctx['slot_c']}/complete",
            json={"rating": 9, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(pro_token),
        )
        assert r.status_code == 200, r.text

        # /interviews/slots — C must NOT be in pro's "Your slots"
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(pro_token))
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert ctx["slot_c"] not in ids, "completed slot must NOT appear in Your slots"
        assert ctx["slot_b"] not in ids, "expired available slot B still hidden"
        assert ctx["slot_a"] in ids, "future available A still visible"

        # /interviews/my-bookings?upcoming_only=false — C MUST still appear, status=completed
        r2 = session.get(
            f"{API}/interviews/my-bookings?upcoming_only=false",
            headers=auth_headers(pro_token),
        )
        assert r2.status_code == 200, r2.text
        rows = r2.json()
        c_row = next((s for s in rows if s.get("id") == ctx["slot_c"]), None)
        assert c_row is not None, "completed slot must still appear in my-bookings"
        assert c_row.get("status") == "completed"
        assert c_row.get("proof_screenshot") == VALID_PROOF


# ---------------------- student side regression ----------------------

class TestStudentSideUntouched:
    def test_student_listing_no_pro_id_only_available_future(self, session, pro_with_three_slots):
        """Student GET /interviews/slots (no pro_id) — must only show available + future slots."""
        ctx = pro_with_three_slots
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(ctx["student"]["token"]))
        assert r.status_code == 200, r.text
        rows = r.json()
        ids = [s["id"] for s in rows]
        # Expired available B must NOT appear; booked C must NOT appear in listing; future available A MUST appear.
        assert ctx["slot_a"] in ids
        assert ctx["slot_b"] not in ids
        assert ctx["slot_c"] not in ids
        # And any returned row must be status=available
        for s in rows:
            if s["id"] in (ctx["slot_a"],):
                assert s.get("status") == "available"

    def test_student_drilldown_with_pro_id_unchanged(self, session, pro_with_three_slots):
        """Student GET /interviews/slots?pro_id=<pro> — full grid (available + booked) but hide expired/cancelled."""
        ctx = pro_with_three_slots
        pro_id = ctx["pro"]["user"]["id"]
        r = session.get(
            f"{API}/interviews/slots?pro_id={pro_id}",
            headers=auth_headers(ctx["student"]["token"]),
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        ids = [s["id"] for s in rows]
        # Future available A AND booked-future C both visible to student in drilldown
        assert ctx["slot_a"] in ids
        assert ctx["slot_c"] in ids
        # Expired B must be hidden from students even in drilldown
        assert ctx["slot_b"] not in ids
        # student_id/student_name on booked C should be redacted for students
        c_row = next((s for s in rows if s["id"] == ctx["slot_c"]), None)
        assert c_row is not None
        if c_row.get("status") == "booked":
            assert c_row.get("student_id") in (None, "")
            assert c_row.get("student_name") in (None, "")


# ---------------------- cancelled slot hidden ----------------------

class TestCancelledHidden:
    def test_pro_your_slots_hides_cancelled(self, session, professional):
        """Manually seed a cancelled slot and assert it's hidden from pro's Your slots."""
        db = _mongo()
        now = datetime.now(timezone.utc)
        slot_id = uuid.uuid4().hex
        db.interview_slots.insert_one({
            "id": slot_id,
            "session_id": uuid.uuid4().hex,
            "pro_id": professional["user"]["id"],
            "pro_name": professional["user"].get("name") or "pro",
            "start_at": _iso(now + timedelta(days=2)),
            "end_at": _iso(now + timedelta(days=2, minutes=30)),
            "scheduled_at": _iso(now + timedelta(days=2)),
            "skill_set": ["TEST_ITER34_CANCEL"],
            "experience_years": 1,
            "topic": "TEST iter34 cancelled",
            "status": "cancelled",
            "student_id": None,
            "student_name": None,
            "meeting_url": "https://meet.example.com/cancel",
            "created_at": _iso(now),
            "_test_marker": "iter34",
        })
        try:
            r = session.get(f"{API}/interviews/slots", headers=auth_headers(professional["token"]))
            assert r.status_code == 200
            ids = [s["id"] for s in r.json()]
            assert slot_id not in ids, "cancelled slot must be hidden from pro's Your slots"
        finally:
            db.interview_slots.delete_one({"id": slot_id})
