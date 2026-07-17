"""Iter67 — Standardized Credit Policy backend delta verification.

Rule under test (unified across fresher + experienced):
  Job Application (professional job)  -> 99 credits
  Mock Interview Booking              -> 99 credits
  Admin Walk-in / Direct Jobs         -> FREE (400 reject; NO deduction)
  Pro Interview reward (unchanged)    -> +110 on completed interview
  Pro Job Post reward (unchanged)     -> +200 one-time at 4th valid app

Delta from Iter51: experienced students used to pay 199. Both now pay 99.
"""
import os
import pytest
from datetime import date, timedelta
from pymongo import MongoClient
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

STANDARD_COST = 99
JOB_POST_REWARD = 200


# ------------- Helpers -------------
def _db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _set_profile_role(user_id: str, preferred_role: str):
    """Complete student profile in Mongo so Iter58 profile-complete gate passes.

    student_missing_fields() reads from user.profile fields directly, so we must
    populate ALL 11 mandatory fields (not just set profile_complete=True).
    """
    d = _db()
    u = d.users.find_one({"id": user_id}) or {}
    prof = u.get("profile") or {}
    prof.update({
        "preferred_role": preferred_role,
        "phone": "+919999912345",
        "phone_verified": True,
        "gender": "male",
        "dob": "2000-01-15",
        "education": "B.Tech",
        "passed_out_year": 2023,
        "skills": ["Python", "SQL"],
        "current_location": "Bengaluru",
        "resume_link": "https://example.com/resume.pdf",
    })
    d.users.update_one(
        {"id": user_id},
        {"$set": {
            "name": u.get("name") or "TEST Student",
            "is_email_verified": True,
            "profile": prof,
            "profile_complete": True,
            "missing_fields": [],
        }},
    )


def _seed_credits(user_id: str, credits: int, free_uses_left: int = 0):
    _db().users.update_one(
        {"id": user_id},
        {"$set": {"credits": credits, "free_uses_left": free_uses_left}},
    )


def _get_user(user_id: str) -> dict:
    return _db().users.find_one({"id": user_id}, {"_id": 0}) or {}


def _future_deadline(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _insert_pro_job(pro_id: str, title: str = "TEST67 Pro Job") -> str:
    from server import new_id, now_iso
    jid = new_id()
    _db().jobs.insert_one({
        "id": jid,
        "employer_id": pro_id,
        "employer_name": "TEST Corp",
        "posted_by_role": "professional",
        "posted_by_name": "TEST Pro",
        "source": "professional",
        "title": title,
        "company": "TEST Corp",
        "description": "Iter67 standardized credit test job.",
        "location": "Bengaluru",
        "locations": ["Bengaluru"],
        "salary_range": "5-8 LPA",
        "salary_range_label": "5-8 LPA",
        "industry_type": "IT Services",
        "skills_required": ["Python"],
        "category": "fresher",
        "experience_required": 0,
        "experience_min": 0,
        "experience_max": 2,
        "open_positions": 5,
        "open_positions_label": "5",
        "status": "open",
        "verification_status": "verified",
        "last_date_to_apply": _future_deadline(30),
        "created_at": now_iso(),
    })
    return jid


def _insert_admin_job(admin_user_id: str, title: str = "TEST67 Admin Walk-in") -> str:
    from server import new_id, now_iso
    jid = new_id()
    _db().jobs.insert_one({
        "id": jid,
        "employer_id": admin_user_id,
        "employer_name": "TEST Walk-in",
        "posted_by_role": "admin",
        "posted_by_name": "Admin",
        "source": "admin",
        "title": title,
        "company": "TEST Walk-in",
        "description": "Iter67 admin walk-in — apply must be rejected 400.",
        "location": "Bengaluru",
        "locations": ["Bengaluru"],
        "skills_required": ["Communication"],
        "category": "fresher",
        "experience_required": 0,
        "experience_min": 0,
        "experience_max": 2,
        "open_positions": 3,
        "open_positions_label": "3",
        "status": "open",
        "verification_status": "verified",
        "last_date_to_apply": _future_deadline(30),
        "created_at": now_iso(),
    })
    return jid


def _insert_interview_slot(pro_id: str, hours_ahead: int = 24) -> str:
    from datetime import datetime, timedelta as td, timezone
    from server import new_id, now_iso
    start = datetime.now(timezone.utc) + td(hours=hours_ahead)
    end = start + td(minutes=30)
    sid = new_id()
    _db().interview_slots.insert_one({
        "id": sid,
        "session_id": new_id(),
        "pro_id": pro_id,
        "pro_name": "TEST Pro",
        "start_at": start.isoformat().replace("+00:00", "Z"),
        "end_at": end.isoformat().replace("+00:00", "Z"),
        "scheduled_at": start.isoformat().replace("+00:00", "Z"),
        "skill_set": ["Python"],
        "experience_years": 0,
        "topic": "TEST",
        "status": "available",
        "student_id": None,
        "student_name": None,
        "meeting_url": f"https://meet.example/{sid[:8]}",
        "created_at": now_iso(),
    })
    return sid


def _get_admin_user_id(admin_token: str, session) -> str:
    r = session.get(f"{API}/auth/me", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    return (data.get("user") or data).get("id")


# ------------- Fixtures -------------
@pytest.fixture()
def fresher(session):
    s = _signup_verify(session, "student", prefix="T67_FR")
    _set_profile_role(s["user"]["id"], "fresher")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def experienced(session):
    s = _signup_verify(session, "student", prefix="T67_EX")
    _set_profile_role(s["user"]["id"], "experienced")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def pro(session):
    p = _signup_verify(session, "professional", prefix="T67_PRO")
    _gmail_verify_in_db(p["user"]["id"])
    return p


# ============================================================
# Case 1 & 2: /subscription/plans action_cost == 99 for both
# ============================================================
class TestSubscriptionPlansCost:
    def test_fresher_plans_action_cost_99(self, session, fresher):
        r = session.get(f"{API}/subscription/plans", headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        pt = r.json().get("paid_tier") or {}
        assert pt.get("action_cost") == STANDARD_COST, f"expected 99, got {pt.get('action_cost')}"

    def test_experienced_plans_action_cost_99(self, session, experienced):
        r = session.get(f"{API}/subscription/plans", headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        pt = r.json().get("paid_tier") or {}
        # Prior iterations returned 199 here — must now be 99.
        assert pt.get("action_cost") == STANDARD_COST, (
            f"REGRESSION: experienced action_cost should be 99, got {pt.get('action_cost')}"
        )

    def test_wallet_action_cost_matches_plans(self, session, fresher, experienced):
        for who in (fresher, experienced):
            r = session.get(f"{API}/wallet", headers=auth_headers(who["token"]))
            assert r.status_code == 200, r.text
            assert r.json().get("action_cost") == STANDARD_COST


# ============================================================
# Case 3 & 4: Job Apply deducts 99 for BOTH categories
# ============================================================
class TestJobApplyStandardCost:
    def test_fresher_apply_charges_99(self, session, fresher, pro):
        job_id = _insert_pro_job(pro["user"]["id"], title="T67 Fresher Apply")
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert before - after == STANDARD_COST, f"fresher delta {before-after} != 99"
        app_doc = _db().applications.find_one(
            {"job_id": job_id, "student_id": fresher["user"]["id"]}
        )
        assert app_doc is not None
        assert app_doc.get("credits_charged") == STANDARD_COST

    def test_experienced_apply_charges_99_not_199(self, session, experienced, pro):
        job_id = _insert_pro_job(pro["user"]["id"], title="T67 Exp Apply")
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        delta = before - after
        assert delta == STANDARD_COST, (
            f"REGRESSION: experienced delta {delta} != 99 (was 199 pre-Iter67)"
        )
        app_doc = _db().applications.find_one(
            {"job_id": job_id, "student_id": experienced["user"]["id"]}
        )
        assert app_doc.get("credits_charged") == STANDARD_COST, (
            f"applications.credits_charged={app_doc.get('credits_charged')} expected 99"
        )


# ============================================================
# Case 5: 98 credits < 99 → Insufficient credits, no apply
# ============================================================
class TestInsufficientCreditsBlock:
    def _make_low_student(self, session, role_tag: str):
        s = _signup_verify(session, "student", prefix=f"T67_LOW_{role_tag[:2].upper()}")
        _set_profile_role(s["user"]["id"], role_tag)
        _seed_credits(s["user"]["id"], 98, free_uses_left=0)  # 1 short of 99
        return s

    def test_fresher_98_credits_blocked_on_apply(self, session, pro):
        s = self._make_low_student(session, "fresher")
        job_id = _insert_pro_job(pro["user"]["id"], title="T67 Low Fresher Apply")
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(s["token"]))
        # Job apply raises 402 for insufficient credits (equivalent to spec's 400 wording).
        assert r.status_code in (400, 402), r.text
        assert "Insufficient credits" in r.json().get("detail", "")
        # No application row and no deduction.
        assert _db().applications.find_one({"job_id": job_id, "student_id": s["user"]["id"]}) is None
        assert _get_user(s["user"]["id"]).get("credits", 0) == 98

    def test_experienced_98_credits_blocked_on_apply(self, session, pro):
        s = self._make_low_student(session, "experienced")
        job_id = _insert_pro_job(pro["user"]["id"], title="T67 Low Exp Apply")
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code in (400, 402), r.text
        assert "Insufficient credits" in r.json().get("detail", "")
        assert _db().applications.find_one({"job_id": job_id, "student_id": s["user"]["id"]}) is None
        assert _get_user(s["user"]["id"]).get("credits", 0) == 98

    def test_fresher_98_credits_blocked_on_book(self, session, pro):
        s = self._make_low_student(session, "fresher")
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=24)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code in (400, 402), r.text
        assert "Insufficient credits" in r.json().get("detail", "")
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot["status"] == "available"

    def test_experienced_98_credits_blocked_on_book(self, session, pro):
        s = self._make_low_student(session, "experienced")
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=25)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code in (400, 402), r.text
        assert "Insufficient credits" in r.json().get("detail", "")


# ============================================================
# Case 6 & 7: Interview booking deducts 99 for both
# ============================================================
class TestInterviewBookStandardCost:
    def test_fresher_book_charges_99(self, session, fresher, pro):
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=26)
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert before - after == STANDARD_COST
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot.get("credits_charged") == STANDARD_COST

    def test_experienced_book_charges_99_not_199(self, session, experienced, pro):
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=27)
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        delta = before - after
        assert delta == STANDARD_COST, (
            f"REGRESSION: experienced interview book delta {delta} != 99 (was 199 pre-Iter67)"
        )
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot.get("credits_charged") == STANDARD_COST

    def test_fresher_book_free_use_first_no_credit_deduction(self, session, pro):
        """free_uses_left must be consumed first; when consumed, no credit deduction."""
        s = _signup_verify(session, "student", prefix="T67_FREE")
        _set_profile_role(s["user"]["id"], "fresher")
        _seed_credits(s["user"]["id"], 1000, free_uses_left=1)
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=28)
        before_c = _get_user(s["user"]["id"]).get("credits", 0)
        before_f = _get_user(s["user"]["id"]).get("free_uses_left", 0)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code == 200, r.text
        after_c = _get_user(s["user"]["id"]).get("credits", 0)
        after_f = _get_user(s["user"]["id"]).get("free_uses_left", 0)
        assert after_c == before_c, "free pass must not deduct credits"
        assert after_f == before_f - 1, "free_uses_left must decrement by 1"
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot.get("credits_charged") == 0


# ============================================================
# Case 8: Admin walk-in job — reject 400, no deduction, no app row
# ============================================================
class TestAdminWalkInBlocked:
    def test_fresher_admin_apply_rejected_no_deduction(self, session, fresher, admin_token):
        admin_uid = _get_admin_user_id(admin_token, session)
        job_id = _insert_admin_job(admin_uid, title="T67 Admin Reject Fresher")
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 400, r.text
        # Message contract preserved
        detail = r.json().get("detail", "")
        detail_s = detail if isinstance(detail, str) else str(detail)
        assert "Admin Walk-in" in detail_s or "walk-in" in detail_s.lower()
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert after == before, f"admin-walk-in must not deduct — delta {before-after}"
        assert _db().applications.find_one(
            {"job_id": job_id, "student_id": fresher["user"]["id"]}
        ) is None

    def test_experienced_admin_apply_rejected_no_deduction(self, session, experienced, admin_token):
        admin_uid = _get_admin_user_id(admin_token, session)
        job_id = _insert_admin_job(admin_uid, title="T67 Admin Reject Exp")
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 400, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        assert after == before


# ============================================================
# Case 9: Pro job_post_reward +200 fires ONCE at 4th valid app
# ============================================================
class TestProJobPostRewardStillWorks:
    def test_reward_200_at_4th_app_once(self, session, pro):
        job_id = _insert_pro_job(pro["user"]["id"], title="T67 Reward Threshold")
        pro_start = _get_user(pro["user"]["id"]).get("credits", 0)
        students = []
        for i in range(5):
            s = _signup_verify(session, "student", prefix=f"T67_APP{i}")
            _set_profile_role(s["user"]["id"], "fresher")
            _seed_credits(s["user"]["id"], 1000)
            students.append(s)

        # First 3 apps → no reward
        for i in range(3):
            r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                             headers=auth_headers(students[i]["token"]))
            assert r.status_code == 200, r.text
        assert _get_user(pro["user"]["id"]).get("credits", 0) == pro_start

        # 4th → +200
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(students[3]["token"]))
        assert r.status_code == 200, r.text
        pro_after_4 = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after_4 - pro_start == JOB_POST_REWARD

        # Reward txn recorded exactly once
        tx_count = _db().transactions.count_documents(
            {"user_id": pro["user"]["id"], "reason": "job_post_reward",
             "meta.job_id": job_id, "delta": JOB_POST_REWARD}
        )
        assert tx_count == 1, f"Expected exactly 1 job_post_reward tx, found {tx_count}"

        # 5th → no double reward
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(students[4]["token"]))
        assert r.status_code == 200, r.text
        pro_after_5 = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after_5 == pro_after_4, "reward must not double-fire on 5th app"


# ============================================================
# Teardown — best-effort cleanup of TEST67 rows
# ============================================================
@pytest.fixture(autouse=True, scope="module")
def _cleanup_after():
    yield
    d = _db()
    d.users.delete_many({"email": {"$regex": "^t67_"}})
    d.jobs.delete_many({"title": {"$regex": "^T67 "}})
    d.applications.delete_many({"job_title": {"$regex": "^T67 "}})
    d.interview_slots.delete_many({"topic": "TEST"})
