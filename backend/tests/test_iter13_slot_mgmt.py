"""Iteration 13 — Mock Interview Slot Management overhaul.

Coverage:
  • Slot auto-split into 30-min sub-slots (multiple-of-30 validation)
  • Pro slot listing (own pro view)
  • Student listing aggregation (/professionals?has_available_slots=true) — slots_total / slots_available / fully_booked
  • Student drill-down (/interviews/slots?pro_id=X) returns FULL grid incl. booked, with student PII stripped
  • Atomic booking (race-safe single-claim)
  • Booking response carries student_email_status / pro_email_status
  • Admin audit log (/admin/interview-bookings) — booking persisted with email status + current_slot_status
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db  # noqa: E402


def _mark_profile_complete(user_id: str):
    """Pro must have profile_complete=True to appear in /api/professionals listing."""
    import os
    from pymongo import MongoClient
    mc = MongoClient(os.environ["MONGO_URL"])
    mc[os.environ["DB_NAME"]].users.update_one(
        {"id": user_id},
        {"$set": {
            "profile_complete": True,
            "profile": {
                "expertise": ["Python", "React"],
                "skills": ["Python", "React"],
                "current_location": "Bangalore",
                "experience_years": 3,
                "company": "Acme",
                "designation": "SDE",
            },
        }},
    )
    mc.close()


@pytest.fixture()
def listed_pro(session):
    """Professional with gmail_verified + profile_complete (eligible for /api/professionals)."""
    pro = _signup_verify(session, "professional", prefix="ITER13PRO")
    _gmail_verify_in_db(pro["user"]["id"])
    _mark_profile_complete(pro["user"]["id"])
    return pro


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _future_session_bounds(hours_from_now: float, minutes: int):
    """Return (start_iso, end_iso) `hours_from_now` away, with given duration in minutes.
    Rounded to nearest minute to avoid float artifacts in the API.
    """
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    start = start.replace(second=0, microsecond=0)
    return _iso(start), _iso(start + timedelta(minutes=minutes))


def _create_slot(session, pro_token, start_iso, end_iso, skill="Python"):
    return session.post(
        f"{API}/interviews/slots",
        headers=auth_headers(pro_token),
        json={
            "start_at": start_iso,
            "end_at": end_iso,
            "skill_set": [skill],
            "experience_years": 3,
            "topic": "DSA",
        },
    )


@pytest.fixture()
def funded_student(session):
    """Student with mock free uses (default 2). Booking 2 sub-slots fits in free tier."""
    return _signup_verify(session, "student", prefix="ITER13")


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

class TestSlotCreationAutoSplit:

    def test_duration_not_multiple_of_30_returns_400(self, session, listed_pro):
        # 45-min session — not multiple of 30
        start_iso, end_iso = _future_session_bounds(48, 45)
        r = _create_slot(session, listed_pro["token"], start_iso, end_iso)
        assert r.status_code == 400, r.text
        assert "multiple of 30" in r.text.lower()

    def test_60min_session_splits_into_two_subslots(self, session, listed_pro):
        start_iso, end_iso = _future_session_bounds(50, 60)
        r = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="React")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["slot_count"] == 2, body
        assert len(body["slots"]) == 2
        s1, s2 = body["slots"]
        # both share the same session_id
        assert s1["session_id"] == s2["session_id"] == body["session_id"]
        # top-level id == first sub-slot id (back-compat shim)
        assert body["id"] == s1["id"]
        # 30 min each
        for s in body["slots"]:
            d = (
                datetime.fromisoformat(s["end_at"].replace("Z", "+00:00"))
                - datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
            ).total_seconds() / 60
            assert d == 30.0, f"sub-slot not 30 min: {d}"
        # contiguous
        assert s1["end_at"] == s2["start_at"]

    def test_pro_listing_returns_two_subslots(self, session, listed_pro):
        start_iso, end_iso = _future_session_bounds(54, 60)
        cr = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="Java")
        assert cr.status_code == 200
        session_id = cr.json()["session_id"]
        r = session.get(f"{API}/interviews/slots", headers=auth_headers(listed_pro["token"]))
        assert r.status_code == 200
        my = [s for s in r.json() if s.get("session_id") == session_id]
        assert len(my) == 2, f"Expected 2 sub-slots, got {len(my)}"


class TestProfessionalListingAggregation:

    def test_listing_includes_pro_with_slots_total_2_available_2(self, session, listed_pro, funded_student):
        start_iso, end_iso = _future_session_bounds(60, 60)
        cr = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="Aggregate")
        assert cr.status_code == 200
        r = session.get(
            f"{API}/professionals?has_available_slots=true",
            headers=auth_headers(funded_student["token"]),
        )
        assert r.status_code == 200, r.text
        match = [p for p in r.json() if p["id"] == listed_pro["user"]["id"]]
        assert match, "Pro must appear in listing when has 2 future available slots"
        p = match[0]
        assert p["slots_total"] == 2, p
        assert p["slots_available"] == 2, p
        assert p["fully_booked"] is False

    def test_student_drilldown_returns_full_grid(self, session, listed_pro, funded_student):
        start_iso, end_iso = _future_session_bounds(66, 60)
        cr = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="Drill")
        assert cr.status_code == 200
        session_id = cr.json()["session_id"]
        # Student drill-down: should include both sub-slots
        r = session.get(
            f"{API}/interviews/slots?pro_id={listed_pro['user']['id']}",
            headers=auth_headers(funded_student["token"]),
        )
        assert r.status_code == 200
        mine = [s for s in r.json() if s.get("session_id") == session_id]
        assert len(mine) == 2, f"Drill-down must return both sub-slots, got {len(mine)}"


class TestBookingFlow:

    def test_full_booking_lifecycle(self, session, listed_pro, funded_student):
        # Create a 60-min session => 2 sub-slots
        start_iso, end_iso = _future_session_bounds(72, 60)
        cr = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="Lifecycle")
        assert cr.status_code == 200
        sub_slots = cr.json()["slots"]
        sid1, sid2 = sub_slots[0]["id"], sub_slots[1]["id"]
        session_id = cr.json()["session_id"]

        # 1) Book first sub-slot
        b1 = session.post(
            f"{API}/interviews/book",
            headers=auth_headers(funded_student["token"]),
            json={"slot_id": sid1},
        )
        assert b1.status_code == 200, b1.text
        b1j = b1.json()
        assert "student_email_status" in b1j and b1j["student_email_status"] in ("sent", "queued")
        assert "pro_email_status" in b1j and b1j["pro_email_status"] in ("sent", "queued")

        # 2) Booking SAME slot again must fail
        dup = session.post(
            f"{API}/interviews/book",
            headers=auth_headers(funded_student["token"]),
            json={"slot_id": sid1},
        )
        assert dup.status_code == 400
        assert "not available" in dup.text.lower()

        # 3) After 1 of 2 booked: listing fully_booked=False, slots_available=1
        plist = session.get(
            f"{API}/professionals?has_available_slots=true",
            headers=auth_headers(funded_student["token"]),
        ).json()
        match = [p for p in plist if p["id"] == listed_pro["user"]["id"]]
        assert match and match[0]["slots_total"] == 2
        assert match[0]["slots_available"] == 1, match[0]
        assert match[0]["fully_booked"] is False

        # 4) Drill-down still returns BOTH; booked sub-slot has student_id=None
        grid = session.get(
            f"{API}/interviews/slots?pro_id={listed_pro['user']['id']}",
            headers=auth_headers(funded_student["token"]),
        ).json()
        mine = [s for s in grid if s.get("session_id") == session_id]
        assert len(mine) == 2
        booked_in_grid = next((s for s in mine if s["id"] == sid1), None)
        assert booked_in_grid is not None
        assert booked_in_grid["status"] == "booked"
        assert booked_in_grid.get("student_id") is None, "Booked slot must strip student_id for students"
        assert booked_in_grid.get("student_name") is None

        # 5) Second student books the OTHER sub-slot — fully booked now
        stu2 = _signup_verify(session, "student", prefix="ITER13B")
        b2 = session.post(
            f"{API}/interviews/book",
            headers=auth_headers(stu2["token"]),
            json={"slot_id": sid2},
        )
        assert b2.status_code == 200, b2.text

        plist2 = session.get(
            f"{API}/professionals?has_available_slots=true",
            headers=auth_headers(funded_student["token"]),
        ).json()
        match2 = [p for p in plist2 if p["id"] == listed_pro["user"]["id"]]
        assert match2, "Pro must STILL appear even when fully booked"
        assert match2[0]["fully_booked"] is True
        assert match2[0]["slots_available"] == 0
        assert match2[0]["slots_total"] == 2


class TestAdminBookingsAudit:

    def test_admin_endpoint_lists_booking_with_email_status(self, session, listed_pro, funded_student, admin_token):
        # create + book one sub-slot
        start_iso, end_iso = _future_session_bounds(80, 30)
        cr = _create_slot(session, listed_pro["token"], start_iso, end_iso, skill="AdminAudit")
        assert cr.status_code == 200
        sid = cr.json()["slots"][0]["id"]
        b = session.post(
            f"{API}/interviews/book",
            headers=auth_headers(funded_student["token"]),
            json={"slot_id": sid},
        )
        assert b.status_code == 200, b.text

        r = session.get(f"{API}/admin/interview-bookings", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        bookings = r.json()
        match = [x for x in bookings if x.get("slot_id") == sid]
        assert match, "Booking must be persisted in interview_bookings collection"
        rec = match[0]
        for k in [
            "student_email", "pro_email", "meeting_url", "booked_at",
            "student_email_status", "pro_email_status", "current_slot_status",
        ]:
            assert k in rec, f"Missing key {k!r} in admin booking record: {rec}"
        assert rec["student_email_status"] in ("sent", "queued")
        assert rec["pro_email_status"] in ("sent", "queued")
        assert rec["current_slot_status"] == "booked"

    def test_admin_endpoint_requires_admin_role(self, session, funded_student):
        r = session.get(
            f"{API}/admin/interview-bookings",
            headers=auth_headers(funded_student["token"]),
        )
        assert r.status_code in (401, 403), r.text
