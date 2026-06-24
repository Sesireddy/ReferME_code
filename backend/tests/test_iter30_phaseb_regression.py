"""Iteration 30 — Phase B (interviews) refactor regression.

Goal: prove that moving /api/interviews/* endpoints from server.py into
routers/interviews.py did not change behaviour, AND that the apply-to-job
path in server.py can still call _can_use_free (i.e. no NameError /
ImportError circular-init crash).

Endpoints exercised:
  POST /api/interviews/slots         (pro, gmail+phone+email verified, skill_set req'd, duration mults of 30)
  GET  /api/interviews/slots         (auth required)
  POST /api/interviews/book          (student; consumes free use OR ACTION_COST credits)
  GET  /api/interviews/my-bookings   (student + pro views)
  POST /api/interviews/{id}/joined   (either party only)
  POST /api/interviews/{id}/complete (pro only; +35 credits, mandatory feedback/proof)
  POST /api/jobs/apply               (student; verifies _can_use_free callable from server.py)
  Phase A regression: refer/validate, refer/me, leaderboard/*

The full /complete happy path is already covered by iter25 — here we focus
on the new (post-refactor) round-trip continuity.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db


# ----------------------------- helpers -----------------------------

def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _future_bounds(hours_from_now: float, minutes: int):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    start = start.replace(second=0, microsecond=0)
    return _iso(start), _iso(start + timedelta(minutes=minutes))


def _mark_phone_verified(user_id: str, phone: str = "+919800099001"):
    """Bypass SMS OTP — flip phone_verified True directly in DB."""
    _mongo().users.update_one(
        {"id": user_id},
        {"$set": {"profile.phone": phone, "profile.phone_verified": True}},
    )


@pytest.fixture()
def verified_pro(session):
    """A pro with email+phone+gmail all verified — eligible to create interview slots."""
    pro = _signup_verify(session, "professional", prefix="ITER30PRO")
    _gmail_verify_in_db(pro["user"]["id"])
    _mark_phone_verified(pro["user"]["id"])
    return pro


@pytest.fixture()
def raw_pro(session):
    """A pro WITHOUT gmail / phone verification — used to assert 403 gating."""
    return _signup_verify(session, "professional", prefix="ITER30RAW")


# ============================================================================
# 1. Backend boots + interviews router mounted (no ImportError crash)
# ============================================================================

class TestBackendBoots:
    def test_root_responds(self, session, base_url):
        r = session.get(f"{base_url}/api/")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("app") == "ReferME"

    def test_interviews_slots_endpoint_mounted(self, session):
        # Without auth, expect 401/403, NOT 404 — confirms router is wired.
        r = session.get(f"{API}/interviews/slots")
        assert r.status_code in (401, 403), f"interviews router NOT mounted, got {r.status_code}: {r.text}"


# ============================================================================
# 2. POST /api/interviews/slots
# ============================================================================

class TestCreateSlot:
    def test_pro_only_student_blocked(self, session, student):
        s, e = _future_bounds(2, 30)
        r = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Python"]},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code in (401, 403), r.text

    def test_unverified_pro_gets_403(self, session, raw_pro):
        # raw_pro has no phone verification → expect 403 from require_phone_verified
        s, e = _future_bounds(3, 30)
        r = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Python"]},
            headers=auth_headers(raw_pro["token"]),
        )
        assert r.status_code == 403, r.text

    def test_skill_set_required(self, session, verified_pro):
        s, e = _future_bounds(4, 30)
        r = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": []},
            headers=auth_headers(verified_pro["token"]),
        )
        assert r.status_code == 400, r.text
        assert "skill" in (r.json().get("detail") or "").lower()

    def test_duration_must_be_multiple_of_30(self, session, verified_pro):
        s, e = _future_bounds(5, 45)  # 45 min — not a multiple of 30
        r = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Python"]},
            headers=auth_headers(verified_pro["token"]),
        )
        assert r.status_code == 400, r.text

    def test_create_slot_happy_path(self, session, verified_pro):
        s, e = _future_bounds(6, 30)
        r = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Python"], "topic": "DSA", "experience_years": 2},
            headers=auth_headers(verified_pro["token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "available"
        assert body.get("session_id")
        assert body.get("slot_count") == 1
        # Cleanup
        _mongo().interview_slots.delete_many({"session_id": body["session_id"]})


# ============================================================================
# 3. GET /api/interviews/slots
# ============================================================================

class TestListSlots:
    def test_requires_auth(self, session):
        r = session.get(f"{API}/interviews/slots")
        assert r.status_code in (401, 403), r.text

    def test_student_sees_pro_slot(self, session, verified_pro, student):
        s, e = _future_bounds(7, 30)
        rc = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["RegressionTest"]},
            headers=auth_headers(verified_pro["token"]),
        )
        assert rc.status_code == 200, rc.text
        session_id = rc.json()["session_id"]
        try:
            r = session.get(f"{API}/interviews/slots", headers=auth_headers(student["token"]))
            assert r.status_code == 200, r.text
            found = [x for x in r.json() if x.get("session_id") == session_id]
            assert found, "student listing must surface the freshly-created available slot"
            for x in found:
                assert x["status"] == "available"
        finally:
            _mongo().interview_slots.delete_many({"session_id": session_id})


# ============================================================================
# 4. POST /api/interviews/book + 5. /my-bookings
# ============================================================================

class TestBookFlow:
    def test_book_consumes_free_use(self, session, verified_pro, student):
        # Student starts with free_uses_left>0 (default for new signups)
        stu_doc = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0, "free_uses_left": 1, "credits": 1})
        free_before = int(stu_doc.get("free_uses_left") or 0)

        s, e = _future_bounds(8, 30)
        rc = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Bookable"]},
            headers=auth_headers(verified_pro["token"]),
        )
        assert rc.status_code == 200, rc.text
        slot_id = rc.json()["id"]
        session_id = rc.json()["session_id"]

        try:
            rb = session.post(
                f"{API}/interviews/book",
                json={"slot_id": slot_id},
                headers=auth_headers(student["token"]),
            )
            assert rb.status_code == 200, rb.text
            assert rb.json().get("message") == "Booked"

            # Slot should now be 'booked' in DB
            slot = _mongo().interview_slots.find_one({"id": slot_id}, {"_id": 0})
            assert slot["status"] == "booked"
            assert slot["student_id"] == student["user"]["id"]

            # Free uses decremented OR credits decremented depending on free pool
            stu_after = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0})
            free_after = int(stu_after.get("free_uses_left") or 0)
            if free_before > 0:
                assert free_after == free_before - 1, "free use should have been consumed"
                assert rb.json().get("used_free") is True

            # /my-bookings as student returns this slot
            rmb = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(student["token"]))
            assert rmb.status_code == 200, rmb.text
            mine = [x for x in rmb.json() if x.get("id") == slot_id]
            assert mine, "student my-bookings must include the just-booked slot"
            assert mine[0]["status"] == "booked"
            assert mine[0].get("counterparty_name")

            # /my-bookings as pro also returns this slot
            rmb_pro = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(verified_pro["token"]))
            assert rmb_pro.status_code == 200, rmb_pro.text
            pmine = [x for x in rmb_pro.json() if x.get("id") == slot_id]
            assert pmine, "pro my-bookings must include the booked slot"
        finally:
            _mongo().interview_slots.delete_many({"session_id": session_id})
            _mongo().interview_bookings.delete_many({"slot_id": slot_id})

    def test_book_consumes_credits_when_no_free_uses(self, session, verified_pro, student):
        ACTION_COST = 49
        # Drain free uses, top up credits to exactly ACTION_COST.
        _mongo().users.update_one(
            {"id": student["user"]["id"]},
            {"$set": {"free_uses_left": 0, "credits": ACTION_COST + 10}},
        )

        s, e = _future_bounds(9, 30)
        rc = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["PaidBook"]},
            headers=auth_headers(verified_pro["token"]),
        )
        assert rc.status_code == 200, rc.text
        slot_id = rc.json()["id"]
        session_id = rc.json()["session_id"]

        try:
            rb = session.post(
                f"{API}/interviews/book",
                json={"slot_id": slot_id},
                headers=auth_headers(student["token"]),
            )
            assert rb.status_code == 200, rb.text
            assert rb.json().get("used_free") is False

            after = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0, "credits": 1})
            assert int(after["credits"]) == 10, f"expected 10 credits after -{ACTION_COST}, got {after['credits']}"
        finally:
            _mongo().interview_slots.delete_many({"session_id": session_id})
            _mongo().interview_bookings.delete_many({"slot_id": slot_id})


# ============================================================================
# 6. POST /api/interviews/{slot_id}/joined  (lightweight — full /complete in iter25)
# ============================================================================

class TestJoinedAndComplete:
    def test_joined_marks_user(self, session, verified_pro, student):
        s, e = _future_bounds(10, 30)
        rc = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["Joined"]},
            headers=auth_headers(verified_pro["token"]),
        )
        slot_id = rc.json()["id"]
        session_id = rc.json()["session_id"]
        try:
            rb = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                              headers=auth_headers(student["token"]))
            assert rb.status_code == 200, rb.text

            rj = session.post(f"{API}/interviews/{slot_id}/joined",
                              headers=auth_headers(student["token"]))
            assert rj.status_code == 200, rj.text
            assert rj.json().get("message") == "Joined"

            slot = _mongo().interview_slots.find_one({"id": slot_id}, {"_id": 0})
            assert student["user"]["id"] in (slot.get("joined_by") or [])
        finally:
            _mongo().interview_slots.delete_many({"session_id": session_id})
            _mongo().interview_bookings.delete_many({"slot_id": slot_id})

    def test_joined_strangers_forbidden(self, session, verified_pro, student):
        s, e = _future_bounds(11, 30)
        rc = session.post(
            f"{API}/interviews/slots",
            json={"start_at": s, "end_at": e, "skill_set": ["JoinedRBAC"]},
            headers=auth_headers(verified_pro["token"]),
        )
        slot_id = rc.json()["id"]
        session_id = rc.json()["session_id"]
        try:
            # student who didn't book → 403
            other = _signup_verify(session, "student", prefix="ITER30NB")
            rj = session.post(f"{API}/interviews/{slot_id}/joined",
                              headers=auth_headers(other["token"]))
            assert rj.status_code == 403, rj.text
            _mongo().users.delete_one({"id": other["user"]["id"]})
        finally:
            _mongo().interview_slots.delete_many({"session_id": session_id})


# ============================================================================
# 7. POST /api/jobs/apply  →  proves _can_use_free is callable from server.py
# ============================================================================

class TestApplyCanUseFree:
    def test_apply_does_not_raise_nameerror(self, session, student):
        """Critical: regression for the deleted-_can_use_free crash.
        We seed a job directly in DB so we don't need an employer flow,
        then hit /api/jobs/apply. Either we get 200 (free use consumed),
        OR a 4xx business error — but NEVER a 500 NameError, which is the
        symptom of the original P0.
        """
        job_id = uuid.uuid4().hex
        _mongo().jobs.insert_one({
            "id": job_id,
            "title": "TEST regression job",
            "description": "iter30",
            "status": "open",
            "employer_id": "TEST_EMPLOYER_iter30",
            "posted_by_role": "employer",
            "created_at": _iso(datetime.now(timezone.utc)),
            "skills": ["Python"],
        })
        try:
            # Ensure student has free uses so this returns 200 cleanly
            _mongo().users.update_one(
                {"id": student["user"]["id"]},
                {"$set": {"free_uses_left": 2, "credits": 0}},
            )
            r = session.post(
                f"{API}/jobs/apply",
                json={"job_id": job_id},
                headers=auth_headers(student["token"]),
            )
            # Must NOT be 500 (NameError/ImportError symptom).
            assert r.status_code != 500, f"_can_use_free regression: {r.status_code} {r.text}"
            assert r.status_code == 200, r.text
            assert r.json().get("message") == "Applied"
            assert r.json().get("used_free") is True
        finally:
            _mongo().jobs.delete_one({"id": job_id})
            _mongo().applications.delete_many({"job_id": job_id})

    def test_apply_consumes_credits_when_no_free(self, session, student):
        ACTION_COST = 49
        job_id = uuid.uuid4().hex
        _mongo().jobs.insert_one({
            "id": job_id,
            "title": "TEST regression paid",
            "status": "open",
            "employer_id": "TEST_EMPLOYER_iter30b",
            "posted_by_role": "employer",
            "created_at": _iso(datetime.now(timezone.utc)),
        })
        _mongo().users.update_one(
            {"id": student["user"]["id"]},
            {"$set": {"free_uses_left": 0, "credits": ACTION_COST + 5}},
        )
        try:
            r = session.post(
                f"{API}/jobs/apply",
                json={"job_id": job_id},
                headers=auth_headers(student["token"]),
            )
            assert r.status_code != 500, r.text
            assert r.status_code == 200, r.text
            assert r.json().get("used_free") is False
            after = _mongo().users.find_one({"id": student["user"]["id"]}, {"_id": 0, "credits": 1})
            assert int(after["credits"]) == 5
        finally:
            _mongo().jobs.delete_one({"id": job_id})
            _mongo().applications.delete_many({"job_id": job_id})


# ============================================================================
# 8. Phase A regression — refer/* + leaderboard/*
# ============================================================================

class TestPhaseARegression:
    def test_refer_validate_invalid(self, session):
        # /refer/validate is a GET with ?code= query param
        r = session.get(f"{API}/refer/validate", params={"code": "BOGUSCODE123"})
        assert r.status_code == 200, r.text
        assert r.json().get("valid") is False

    def test_refer_validate_empty(self, session):
        r = session.get(f"{API}/refer/validate", params={"code": ""})
        assert r.status_code == 200
        # Empty code is treated as "valid" (no inline feedback) per current logic
        assert r.json().get("valid") in (True, False)

    def test_refer_me_returns_user_code(self, session, student):
        r = session.get(f"{API}/refer/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        # Newly-signed-up users may not have a code yet — endpoint must still respond 200.
        assert "code" in body or "referral_code" in body or "link" in body

    def test_leaderboard_professionals(self, session, student):
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), (list, dict))

    def test_leaderboard_students(self, session, student):
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text

    def test_leaderboard_student_me_ranks(self, session, student):
        r = session.get(f"{API}/leaderboard/student/me/ranks", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text

    def test_leaderboard_pro_me_stats(self, session, verified_pro):
        r = session.get(f"{API}/leaderboard/professional/me/stats",
                        headers=auth_headers(verified_pro["token"]))
        assert r.status_code == 200, r.text
