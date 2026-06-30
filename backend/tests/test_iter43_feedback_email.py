"""Iteration 43 — Feedback email + canViewFeedback simplification.

Verifies that when a professional marks an interview slot complete:
- The /complete endpoint still returns 200 and applies all existing side effects
  (+35 credits to pro, slot transitions to completed, candidate_rating + feedback
   persisted to slot doc, student interviews_attended++, student_rating aggregate).
- The backend log line emitted by server.send_html_email contains either
  "Resend OK to=<student_email> subject=ReferME · Your mock interview feedback (<rating>/10)"
  OR "[MOCK-EMAIL] ... purpose=mock_interview_feedback" — either is acceptable.
- When send_html_email raises (monkeypatched), /complete STILL returns 200 and the
  slot still transitions to status=completed (try/except guard).
- /interviews/my-bookings (student) returns the slot with status=completed +
  candidate_rating + feedback fields so the FE can render the View feedback panel.
"""
import os
import re
import time
import uuid
import importlib
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient

from conftest import API, auth_headers


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_booked_slot(pro_id: str, pro_name: str, student_id: str, student_name: str,
                      start_at: datetime, end_at: datetime,
                      student_email: str = "") -> str:
    slot_id = uuid.uuid4().hex
    _mongo().interview_slots.insert_one({
        "id": slot_id,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro_id,
        "pro_name": pro_name,
        "start_at": _iso(start_at),
        "end_at": _iso(end_at),
        "scheduled_at": _iso(start_at),
        "skill_set": ["TEST_iter43"],
        "experience_years": 2,
        "topic": "TEST iter43",
        "status": "booked",
        "student_id": student_id,
        "student_name": student_name,
        "student_email": student_email or f"{student_name}@example.com",
        "meeting_url": f"https://meet.example.com/iter43-{slot_id[:8]}",
        "booked_at": _iso(datetime.now(timezone.utc)),
        "created_at": _iso(datetime.now(timezone.utc)),
        "_test_marker": "iter43",
    })
    return slot_id


VALID_FEEDBACK = "Strong fundamentals, clear communication, work on system-design depth."  # >=20
VALID_PROOF = "data:image/png;base64," + ("A" * 40)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _mongo().interview_slots.delete_many({"_test_marker": "iter43"})


# ---------- backend log helpers ----------
LOG_PATH = "/var/log/supervisor/backend.out.log"
LOG_ERR_PATH = "/var/log/supervisor/backend.err.log"


def _read_logs_since(offset_out: int, offset_err: int) -> str:
    out = ""
    try:
        with open(LOG_PATH, "rb") as f:
            f.seek(offset_out)
            out += f.read().decode("utf-8", errors="ignore")
    except FileNotFoundError:
        pass
    try:
        with open(LOG_ERR_PATH, "rb") as f:
            f.seek(offset_err)
            out += f.read().decode("utf-8", errors="ignore")
    except FileNotFoundError:
        pass
    return out


def _log_offsets():
    o, e = 0, 0
    try:
        o = os.path.getsize(LOG_PATH)
    except OSError:
        pass
    try:
        e = os.path.getsize(LOG_ERR_PATH)
    except OSError:
        pass
    return o, e


class TestCompleteHappyPathStillWorks:
    """Re-validates iter32/iter37/iter38 contract: /complete returns 200 + side effects."""

    def test_complete_returns_200_with_all_side_effects(self, session, professional, student):
        # Snapshot
        before = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
        credits_before = int((before.json().get("user") or {}).get("credits") or 0)
        stu_before = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0})
        ia_before = int(stu_before.get("interviews_attended") or 0)

        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], professional["user"]["name"],
            student["user"]["id"], student["user"]["name"],
            now - timedelta(minutes=3), now + timedelta(minutes=27),
            student_email=student["email"],
        )

        r = session.post(
            f"{API}/interviews/{slot_id}/complete",
            json={"rating": 8, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["earned"] == 35
        assert data["candidate_rating"] == 8
        assert isinstance(data.get("pro_rating"), (int, float))

        # +35 credits
        after = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
        credits_after = int((after.json().get("user") or {}).get("credits") or 0)
        assert credits_after - credits_before == 35

        # slot persisted
        slot = _mongo().interview_slots.find_one({"id": slot_id}, {"_id": 0})
        assert slot["status"] == "completed"
        assert slot["candidate_rating"] == 8
        assert VALID_FEEDBACK[:20] in slot.get("candidate_feedback", "")

        # student aggregate refreshed
        stu_after = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0})
        assert int(stu_after.get("interviews_attended") or 0) == ia_before + 1
        assert float(stu_after.get("student_rating") or 0) > 0

        # /my-bookings (student) shows the slot with feedback + rating
        stu_book = session.get(
            f"{API}/interviews/my-bookings?upcoming_only=false",
            headers=auth_headers(student["token"]),
        )
        assert stu_book.status_code == 200
        rows = [x for x in stu_book.json() if x["id"] == slot_id]
        assert rows, "slot must appear in student my-bookings"
        row = rows[0]
        assert row["status"] == "completed"
        assert row.get("candidate_rating") == 8
        # NOTE (iter43): the FE my-mock-interviews.tsx reads b.feedback, but the backend
        # stores the written feedback under candidate_feedback. Either key is fine for
        # this regression assertion — we just need the text persisted somewhere
        # student-visible. Failure here means student would see "No written feedback"
        # in the View feedback panel even when the pro DID write feedback.
        feedback_visible = (row.get("feedback") or row.get("candidate_feedback") or "")
        assert VALID_FEEDBACK[:20] in feedback_visible, (
            f"feedback not returned to student. Row keys: {sorted(row.keys())}"
        )
        # Specifically also flag the FE-key mismatch so main agent sees it
        assert "feedback" in row, (
            "BUG: backend /interviews/my-bookings returns candidate_feedback "
            "but the student FE (my-mock-interviews.tsx) reads b.feedback — "
            "student's View-feedback panel will show 'No written feedback was provided'."
        )
        # iter25 contract: proof must not leak to student
        assert "proof_screenshot" not in row


class TestFeedbackEmailEmitted:
    """A log line for the candidate feedback email must appear after /complete."""

    def test_resend_or_mock_log_emitted(self, session, professional, student):
        off_out, off_err = _log_offsets()

        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], professional["user"]["name"],
            student["user"]["id"], student["user"]["name"],
            now - timedelta(minutes=2), now + timedelta(minutes=28),
            student_email=student["email"],
        )
        r = session.post(
            f"{API}/interviews/{slot_id}/complete",
            json={"rating": 7, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text

        # The Resend global throttle (~0.55s) means the feedback email may be queued
        # behind the existing booking emails. Allow up to ~5s.
        deadline = time.time() + 6.0
        text = ""
        found_resend = False
        found_mock = False
        while time.time() < deadline:
            text = _read_logs_since(off_out, off_err)
            # Look for the iter43 subject line ANY time after /complete:
            if re.search(
                r"Resend OK to=" + re.escape(student["email"])
                + r".*?ReferME .* Your mock interview feedback \(7/10\)",
                text,
            ):
                found_resend = True
                break
            if "purpose=mock_interview_feedback" in text:
                found_mock = True
                break
            time.sleep(0.4)

        assert found_resend or found_mock, (
            "Expected either 'Resend OK ... subject=ReferME · Your mock interview feedback (7/10)' "
            "or '[MOCK-EMAIL] ... purpose=mock_interview_feedback' in backend logs. "
            f"Captured tail (last 1500 chars):\n{text[-1500:]}"
        )


class TestFeedbackEmailFailureGuard:
    """If send_html_email raises during /complete, the endpoint must still return 200."""

    def test_email_exception_does_not_break_complete(self, session, professional, student, monkeypatch):
        # We need to monkeypatch the SAME function reference used inside routers/interviews.py.
        # That module imported `send_html_email` from server, so we patch the binding inside
        # the router module too.
        import sys
        import importlib

        # Ensure routers.interviews is loaded
        if "routers.interviews" not in sys.modules:
            try:
                importlib.import_module("routers.interviews")
            except Exception:
                pass

        # NOTE: routers.interviews runs INSIDE the live backend process; monkeypatching
        # this test process does NOT affect it. So instead of monkeypatching, we exercise
        # the guarded path by triggering a real provider error via a malformed recipient
        # email — Resend rejects it, but the try/except still must keep /complete green.
        # Seed slot with an invalid email so the Resend API raises.
        now = datetime.now(timezone.utc)
        slot_id = _seed_booked_slot(
            professional["user"]["id"], professional["user"]["name"],
            student["user"]["id"], student["user"]["name"],
            now - timedelta(minutes=2), now + timedelta(minutes=28),
            student_email=student["email"],
        )
        # Force the student's email to an invalid value so Resend raises.
        bad_email = "not-a-real-email-address-xyz"
        _mongo().users.update_one({"id": student["user"]["id"]}, {"$set": {"email": bad_email}})
        try:
            r = session.post(
                f"{API}/interviews/{slot_id}/complete",
                json={"rating": 6, "feedback": VALID_FEEDBACK, "proof_screenshot": VALID_PROOF},
                headers=auth_headers(professional["token"]),
            )
            assert r.status_code == 200, r.text
            # Slot still transitioned
            slot = _mongo().interview_slots.find_one({"id": slot_id}, {"_id": 0})
            assert slot["status"] == "completed"
            assert slot["candidate_rating"] == 6
        finally:
            # Restore email so other tests using the same student don't break (the
            # `student` fixture is function-scoped so cleanup happens anyway, but
            # be defensive).
            _mongo().users.update_one(
                {"id": student["user"]["id"]},
                {"$set": {"email": student["email"]}},
            )
