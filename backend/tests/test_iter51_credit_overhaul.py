"""Iter51 — Credit System (updated for Iter 67 standardized policy).

As of Iter 67, ALL Job Seekers pay the same 99 credits per action regardless of
category. The `EXPERIENCED_COST` constant is retained for legacy references but now
equals `FRESHER_COST` (both 99).

  All Job Seekers     -> 99 credits per action
  Interview reward    -> +110 credits per completed mock interview
  Job-post reward     -> +200 one-time when a pro-posted job reaches 4 valid apps
  Admin Walk-in jobs  -> FREE (no deduction; apply endpoint rejects with 400)
"""
import os
import uuid
import pytest
from pymongo import MongoClient
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db  # noqa: E402


MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

FRESHER_COST = 99
EXPERIENCED_COST = 99  # Iter 67: unified with fresher cost
INTERVIEW_REWARD = 110
JOB_POST_REWARD = 200


# ============================================================
# Helpers
# ============================================================
def _db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _set_profile_role(user_id: str, preferred_role: str):
    """Set only the preferred_role on the profile — do NOT touch profile_complete."""
    d = _db()
    u = d.users.find_one({"id": user_id})
    prof = (u or {}).get("profile") or {}
    prof["preferred_role"] = preferred_role
    d.users.update_one({"id": user_id}, {"$set": {"profile": prof}})


def _seed_credits(user_id: str, credits: int, free_uses_left: int = 0):
    _db().users.update_one(
        {"id": user_id},
        {"$set": {"credits": credits, "free_uses_left": free_uses_left}},
    )


def _get_user(user_id: str) -> dict:
    u = _db().users.find_one({"id": user_id}, {"_id": 0})
    return u or {}


def _insert_pro_job(pro_id: str, title: str = "TEST Pro Job") -> str:
    from server import new_id, now_iso  # local import to reuse helpers
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
        "description": "Test job description for iteration 51 credit-overhaul suite.",
        "location": "Bengaluru",
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
        "created_at": now_iso(),
    })
    return jid


def _insert_admin_job(admin_user_id: str, title: str = "TEST Admin Walk-in") -> str:
    from server import new_id, now_iso
    jid = new_id()
    _db().jobs.insert_one({
        "id": jid,
        "employer_id": admin_user_id,
        "employer_name": "TEST Walk-in Corp",
        "posted_by_role": "admin",
        "posted_by_name": "Admin",
        "source": "admin",
        "title": title,
        "company": "TEST Walk-in Corp",
        "description": "Test admin walk-in job — apply must be rejected 400.",
        "location": "Bengaluru",
        "skills_required": ["Communication"],
        "category": "fresher",
        "experience_required": 0,
        "experience_min": 0,
        "experience_max": 2,
        "open_positions": 3,
        "open_positions_label": "3",
        "status": "open",
        "verification_status": "verified",
        "created_at": now_iso(),
    })
    return jid


def _insert_interview_slot(pro_id: str, hours_ahead: int = 24) -> str:
    """Insert an available interview slot directly (bypasses gmail/phone gate)."""
    from datetime import datetime, timedelta, timezone
    from server import new_id, now_iso
    start = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    end = start + timedelta(minutes=30)
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


# Fixtures for category-tagged students
@pytest.fixture()
def fresher(session):
    s = _signup_verify(session, "student", prefix="TEST_FR")
    _set_profile_role(s["user"]["id"], "fresher")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def experienced(session):
    s = _signup_verify(session, "student", prefix="TEST_EX")
    _set_profile_role(s["user"]["id"], "experienced")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def pro(session):
    p = _signup_verify(session, "professional", prefix="TEST_PRO")
    _gmail_verify_in_db(p["user"]["id"])
    return p


# ============================================================
# GET /wallet -> action_cost by category
# ============================================================
class TestWalletActionCost:
    def test_wallet_fresher_action_cost_99(self, session, fresher):
        r = session.get(f"{API}/wallet", headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("action_cost") == FRESHER_COST

    def test_wallet_experienced_action_cost_199(self, session, experienced):
        r = session.get(f"{API}/wallet", headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("action_cost") == EXPERIENCED_COST

    def test_wallet_pro_action_cost_zero(self, session, pro):
        r = session.get(f"{API}/wallet", headers=auth_headers(pro["token"]))
        assert r.status_code == 200, r.text
        # Non-students should be 0 (spec).
        assert r.json().get("action_cost") == 0


# ============================================================
# GET /auth/me -> action_cost only for students
# ============================================================
class TestAuthMeActionCost:
    def test_me_fresher_has_cost_99(self, session, fresher):
        r = session.get(f"{API}/auth/me", headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        payload = r.json()
        user = payload.get("user") or payload
        assert user.get("action_cost") == FRESHER_COST
        assert user.get("role") == "student"

    def test_me_experienced_has_cost_199(self, session, experienced):
        r = session.get(f"{API}/auth/me", headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        payload = r.json()
        user = payload.get("user") or payload
        assert user.get("action_cost") == EXPERIENCED_COST

    def test_me_pro_has_no_action_cost_key(self, session, pro):
        r = session.get(f"{API}/auth/me", headers=auth_headers(pro["token"]))
        assert r.status_code == 200, r.text
        payload = r.json()
        user = payload.get("user") or payload
        # Spec: action_cost only surfaced for students.
        assert "action_cost" not in user, f"unexpected action_cost on non-student: {user.get('action_cost')}"


# ============================================================
# POST /interviews/book — credit deduction per category
# ============================================================
class TestBookInterviewCredits:
    def test_book_fresher_charged_99(self, session, fresher, pro):
        slot_id = _insert_interview_slot(pro["user"]["id"])
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert before - after == FRESHER_COST, f"Fresher must be charged {FRESHER_COST}, delta={before-after}"
        # Transaction row must exist for -99
        tx = _db().transactions.find_one(
            {"user_id": fresher["user"]["id"], "reason": "interview_booking", "delta": -FRESHER_COST}
        )
        assert tx is not None, "interview_booking -99 tx not found"
        # credits_charged persisted on slot
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot["credits_charged"] == FRESHER_COST

    def test_book_experienced_charged_199(self, session, experienced, pro):
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=48)
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        assert before - after == EXPERIENCED_COST
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot["credits_charged"] == EXPERIENCED_COST

    def test_book_insufficient_credits_blocked_and_slot_rolled_back(self, session, pro):
        # Fresh student with only 50 credits (< 99)
        s = _signup_verify(session, "student", prefix="TEST_LOW")
        _set_profile_role(s["user"]["id"], "fresher")
        _seed_credits(s["user"]["id"], 50)
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=72)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code == 400, r.text
        assert "Insufficient credits" in r.json().get("detail", "")
        # Slot must roll back to available
        slot = _db().interview_slots.find_one({"id": slot_id})
        assert slot["status"] == "available"
        assert slot.get("student_id") in (None, "")


# ============================================================
# POST /jobs/apply — credit deduction, free pass, admin rejection
# ============================================================
class TestJobApplyCredits:
    def test_apply_fresher_charged_99_and_persisted(self, session, fresher, pro):
        job_id = _insert_pro_job(pro["user"]["id"], title="TEST Fresher Apply Job")
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert before - after == FRESHER_COST
        assert r.json().get("used_free") is False
        app_doc = _db().applications.find_one({"job_id": job_id, "student_id": fresher["user"]["id"]})
        assert app_doc is not None
        assert app_doc.get("credits_charged") == FRESHER_COST

    def test_apply_experienced_charged_199(self, session, experienced, pro):
        job_id = _insert_pro_job(pro["user"]["id"], title="TEST Exp Apply Job")
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        assert before - after == EXPERIENCED_COST
        app_doc = _db().applications.find_one({"job_id": job_id, "student_id": experienced["user"]["id"]})
        assert app_doc.get("credits_charged") == EXPERIENCED_COST

    def test_apply_free_use_consumes_pass_no_deduction(self, session, pro):
        s = _signup_verify(session, "student", prefix="TEST_FREE")
        _set_profile_role(s["user"]["id"], "fresher")
        _seed_credits(s["user"]["id"], 1000, free_uses_left=1)
        job_id = _insert_pro_job(pro["user"]["id"], title="TEST Free Apply Job")
        before_credits = _get_user(s["user"]["id"]).get("credits", 0)
        before_free = _get_user(s["user"]["id"]).get("free_uses_left", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(s["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("used_free") is True
        after_credits = _get_user(s["user"]["id"]).get("credits", 0)
        after_free = _get_user(s["user"]["id"]).get("free_uses_left", 0)
        assert after_credits == before_credits, "free pass must not deduct credits"
        assert after_free == before_free - 1, "free_uses_left must decrement by 1"
        app_doc = _db().applications.find_one({"job_id": job_id, "student_id": s["user"]["id"]})
        assert app_doc.get("credits_charged") == 0

    def test_apply_admin_job_rejected(self, session, fresher, admin_token):
        admin_uid = _get_admin_user_id(admin_token, session)
        job_id = _insert_admin_job(admin_uid, title="TEST Admin Walk-in Reject")
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 400, r.text
        # No deduction
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert after == before
        # No application row
        assert _db().applications.find_one({"job_id": job_id, "student_id": fresher["user"]["id"]}) is None


# ============================================================
# POST /interviews/{slot_id}/complete — Pro reward = +110
# ============================================================
class TestInterviewCompleteReward:
    def test_complete_awards_pro_110_credits(self, session, fresher, pro):
        # Book a slot with a Fresher student
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=-1)  # already started
        # Direct-book (bypass /book) to avoid time-window issues and focus on completion
        from server import now_iso
        _db().interview_slots.update_one(
            {"id": slot_id},
            {"$set": {
                "status": "booked",
                "student_id": fresher["user"]["id"],
                "student_name": fresher["user"].get("name") or "TEST Fresher",
                "student_email": fresher["email"],
                "booked_at": now_iso(),
                "credits_charged": FRESHER_COST,
            }},
        )
        # Backdate start_at so 'complete' passes the "start must have passed" gate
        from datetime import datetime, timedelta, timezone
        past_start = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat().replace("+00:00", "Z")
        past_end = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
        _db().interview_slots.update_one({"id": slot_id}, {"$set": {"start_at": past_start, "end_at": past_end}})

        pro_before = _get_user(pro["user"]["id"]).get("credits", 0)
        payload = {
            "rating": 8,
            "feedback": "Great candidate — clear communication and solid fundamentals.",
            "proof_screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=",
        }
        r = session.post(f"{API}/interviews/{slot_id}/complete", json=payload,
                         headers=auth_headers(pro["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("earned") == INTERVIEW_REWARD
        pro_after = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after - pro_before == INTERVIEW_REWARD, f"Pro must earn {INTERVIEW_REWARD} on complete"
        # Transaction row
        tx = _db().transactions.find_one(
            {"user_id": pro["user"]["id"], "reason": "mock_interview_reward", "delta": INTERVIEW_REWARD}
        )
        assert tx is not None, "mock_interview_reward +110 tx missing"


# ============================================================
# Job Post reward: +200 once at 4 apps; NOT on 5th
# ============================================================
class TestJobPostReward:
    def test_reward_paid_once_on_4th_application_not_on_5th(self, session, pro, admin_token):
        job_id = _insert_pro_job(pro["user"]["id"], title="TEST Reward Threshold Job")
        pro_start = _get_user(pro["user"]["id"]).get("credits", 0)

        student_tokens = []
        for i in range(5):
            s = _signup_verify(session, "student", prefix=f"TEST_APP{i}")
            _set_profile_role(s["user"]["id"], "fresher")
            _seed_credits(s["user"]["id"], 1000)
            student_tokens.append(s)

        # Apply 3 times → no reward yet
        for i in range(3):
            r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                             headers=auth_headers(student_tokens[i]["token"]))
            assert r.status_code == 200, r.text

        pro_after_3 = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after_3 == pro_start, "Reward must NOT be paid before 4th application"

        # 4th application → triggers reward
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(student_tokens[3]["token"]))
        assert r.status_code == 200, r.text
        pro_after_4 = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after_4 - pro_start == JOB_POST_REWARD, "Pro must earn +200 exactly at 4th app"
        # posting_reward_paid persisted
        job = _db().jobs.find_one({"id": job_id})
        assert job.get("posting_reward_paid") is True
        # Transaction exists
        tx = _db().transactions.find_one(
            {"user_id": pro["user"]["id"], "reason": "job_post_reward", "delta": JOB_POST_REWARD}
        )
        assert tx is not None, "job_post_reward +200 tx missing"

        # 5th application must NOT double-pay
        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id},
                         headers=auth_headers(student_tokens[4]["token"]))
        assert r.status_code == 200, r.text
        pro_after_5 = _get_user(pro["user"]["id"]).get("credits", 0)
        assert pro_after_5 == pro_after_4, "Reward must NOT be paid twice on 5th app"


# ============================================================
# DELETE /admin/interviews/{slot_id} — refund exact credits_charged
# ============================================================
class TestAdminCancelSlotRefund:
    def test_admin_delete_refunds_99_for_fresher(self, session, fresher, pro, admin_token):
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=96)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        before = _get_user(fresher["user"]["id"]).get("credits", 0)
        r = session.delete(f"{API}/admin/interviews/{slot_id}",
                           headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        after = _get_user(fresher["user"]["id"]).get("credits", 0)
        assert after - before == FRESHER_COST, f"Fresher must be refunded {FRESHER_COST}"

    def test_admin_delete_refunds_199_for_experienced(self, session, experienced, pro, admin_token):
        slot_id = _insert_interview_slot(pro["user"]["id"], hours_ahead=120)
        r = session.post(f"{API}/interviews/book", json={"slot_id": slot_id},
                         headers=auth_headers(experienced["token"]))
        assert r.status_code == 200, r.text
        before = _get_user(experienced["user"]["id"]).get("credits", 0)
        r = session.delete(f"{API}/admin/interviews/{slot_id}",
                           headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        after = _get_user(experienced["user"]["id"]).get("credits", 0)
        assert after - before == EXPERIENCED_COST
