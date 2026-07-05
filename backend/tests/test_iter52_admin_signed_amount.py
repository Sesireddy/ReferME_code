"""Iter52 — Admin transactions/search + stats/overview must read the signed
credit amount from the `delta` field (not the non-existent `amount` field).

Verifies the two-line fix in server.py (~L2849 and L3013):
    amt = int(t.get("delta", t.get("amount", 0)) or 0)

Covers the 5 items from the review request:
  1. /admin/transactions/search returns non-zero signed `amount`,
     `credits_added` (>0 gains) and `credits_deducted` (<0 spends).
  2. `limit` pagination + `type=interview_reward` (and other type_map values)
     continue to work.
  3. /admin/stats/overview `credits` bucket has non-zero purchased / used /
     earned / rewarded values (across the whole DB — 1877 existing txns).
  4. New transactions written after the fix (book-then-admin-cancel Mock
     Interview) show up with the correct signed amount:
        -99 (interview_booking) and +99 (interview_admin_refund).
  5. Regression: /api/wallet still returns raw txns containing the `delta`
     field (endpoint untouched).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _set_profile_role(user_id: str, preferred_role: str):
    d = _db()
    u = d.users.find_one({"id": user_id})
    prof = (u or {}).get("profile") or {}
    prof["preferred_role"] = preferred_role
    d.users.update_one({"id": user_id}, {"$set": {"profile": prof}})


def _seed_credits(user_id: str, credits: int):
    _db().users.update_one({"id": user_id}, {"$set": {"credits": credits, "free_uses_left": 0}})


def _insert_interview_slot(pro_id: str, hours_ahead: int = 26) -> str:
    from server import new_id, now_iso
    start = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    end = start + timedelta(minutes=30)
    sid = new_id()
    _db().interview_slots.insert_one({
        "id": sid,
        "session_id": new_id(),
        "pro_id": pro_id,
        "pro_name": "TEST Pro Iter52",
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


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture()
def fresher(session):
    s = _signup_verify(session, "student", prefix="TEST_I52_FR")
    _set_profile_role(s["user"]["id"], "fresher")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def experienced(session):
    s = _signup_verify(session, "student", prefix="TEST_I52_EX")
    _set_profile_role(s["user"]["id"], "experienced")
    _seed_credits(s["user"]["id"], 1000)
    return s


@pytest.fixture()
def pro(session):
    p = _signup_verify(session, "professional", prefix="TEST_I52_PRO")
    _gmail_verify_in_db(p["user"]["id"])
    return p


# ============================================================
# 1) /admin/transactions/search returns signed amounts
# ============================================================
class TestAdminTransactionsSignedAmount:
    def test_search_returns_non_zero_signed_amounts(self, session, admin_token):
        r = session.get(f"{API}/admin/transactions/search", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0, "Expected historical transactions in DB"

        # Overall bucket sanity
        non_zero = [x for x in rows if x.get("amount", 0) != 0]
        assert len(non_zero) > 0, (
            "Every row has amount=0 — regression of the delta/amount fix. "
            "Total rows=%d" % len(rows)
        )
        # Should be a strong majority (historical -0 bug had 100% zeros).
        assert len(non_zero) / len(rows) > 0.5, (
            f"Only {len(non_zero)}/{len(rows)} rows have non-zero amount"
        )

    def test_credits_added_positive_for_reward_rows(self, session, admin_token):
        r = session.get(f"{API}/admin/transactions/search", headers=auth_headers(admin_token))
        assert r.status_code == 200
        rows = r.json()
        # For every row: credits_added>0 <=> amount>0, credits_deducted>0 <=> amount<0
        for row in rows:
            amt = row.get("amount", 0)
            ca = row.get("credits_added", 0)
            cd = row.get("credits_deducted", 0)
            if amt > 0:
                assert ca == amt and cd == 0, f"Row {row.get('id')} has amt={amt} but ca={ca} cd={cd}"
            elif amt < 0:
                assert cd == -amt and ca == 0, f"Row {row.get('id')} has amt={amt} but ca={ca} cd={cd}"
            else:
                assert ca == 0 and cd == 0

    def test_positive_rewards_present(self, session, admin_token):
        """At least a few reward-type rows must have positive amount."""
        r = session.get(
            f"{API}/admin/transactions/search",
            headers=auth_headers(admin_token),
            params={"type": "interview_reward", "limit": 500},
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        # Not every deployment has 500 rows, but if any exist they must be positive.
        for row in rows:
            assert row.get("reason") == "interview_pro_reward"
            assert row.get("amount", 0) > 0, f"Interview reward row {row.get('id')} has non-positive amount"
            assert row.get("credits_added", 0) > 0
            assert row.get("credits_deducted", 0) == 0

    def test_negative_spends_present(self, session, admin_token):
        """job_application (type=application) spends must be negative."""
        r = session.get(
            f"{API}/admin/transactions/search",
            headers=auth_headers(admin_token),
            params={"type": "application", "limit": 500},
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        for row in rows:
            assert row.get("reason") == "job_application"
            assert row.get("amount", 0) < 0, f"job_application row {row.get('id')} has non-negative amount"
            assert row.get("credits_deducted", 0) > 0
            assert row.get("credits_added", 0) == 0


# ============================================================
# 2) Pagination + type filter regression
# ============================================================
class TestAdminSearchFilters:
    def test_limit_pagination(self, session, admin_token):
        r5 = session.get(f"{API}/admin/transactions/search", headers=auth_headers(admin_token), params={"limit": 5})
        assert r5.status_code == 200
        assert len(r5.json()) <= 5

        r50 = session.get(f"{API}/admin/transactions/search", headers=auth_headers(admin_token), params={"limit": 50})
        assert r50.status_code == 200
        assert len(r50.json()) <= 50
        assert len(r50.json()) >= len(r5.json())

    @pytest.mark.parametrize("type_val,expected_reasons", [
        ("purchase", {"wallet_deposit", "wallet_deposit_confirm", "credit_purchase"}),
        ("application", {"job_application"}),
        ("interview_reward", {"interview_pro_reward"}),
        ("job_post_reward", {"job_post_reward"}),
        ("hiring_reward", {"hiring_reward", "referral_hired_reward"}),
        ("manual", {"admin_refund", "admin_adjustment"}),
    ])
    def test_type_filter_only_returns_mapped_reasons(self, session, admin_token, type_val, expected_reasons):
        r = session.get(
            f"{API}/admin/transactions/search",
            headers=auth_headers(admin_token),
            params={"type": type_val, "limit": 100},
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        for row in rows:
            assert row.get("reason") in expected_reasons, (
                f"type={type_val} returned reason={row.get('reason')} not in {expected_reasons}"
            )


# ============================================================
# 3) /admin/stats/overview credits bucket is non-zero
# ============================================================
class TestAdminStatsCredits:
    def test_credits_buckets_non_zero(self, session, admin_token):
        r = session.get(f"{API}/admin/stats/overview", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        credits = r.json().get("credits") or {}
        # All four buckets should exist as keys
        for k in ("purchased", "used", "earned", "rewarded"):
            assert k in credits, f"Missing key {k} in credits bucket"
        # At least three of the four should be strictly positive on a live DB
        positives = sum(1 for v in credits.values() if v and v > 0)
        assert positives >= 3, f"Only {positives}/4 credit buckets positive: {credits}"

    def test_used_includes_job_application_and_interview_booking(self, session, admin_token):
        # Sum from raw DB
        d = _db()
        expected_used = 0
        for t in d.transactions.find({"reason": {"$in": ["job_application", "interview_booking"]}}, {"delta": 1}):
            expected_used += -int(t.get("delta") or 0) if int(t.get("delta") or 0) < 0 else 0
        r = session.get(f"{API}/admin/stats/overview", headers=auth_headers(admin_token))
        used = r.json()["credits"]["used"]
        assert used == expected_used, f"used={used} but DB expected {expected_used}"

    def test_rewarded_includes_all_reward_reasons(self, session, admin_token):
        d = _db()
        reward_reasons = ["interview_pro_reward", "job_post_reward", "hiring_reward",
                          "referral_hired_reward", "mock_interview_reward"]
        expected_rewarded = 0
        for t in d.transactions.find({"reason": {"$in": reward_reasons}}, {"delta": 1}):
            amt = int(t.get("delta") or 0)
            if amt > 0:
                expected_rewarded += amt
        r = session.get(f"{API}/admin/stats/overview", headers=auth_headers(admin_token))
        rewarded = r.json()["credits"]["rewarded"]
        assert rewarded == expected_rewarded, f"rewarded={rewarded} but DB expected {expected_rewarded}"


# ============================================================
# 4) New book→admin-cancel flow shows signed amounts
# ============================================================
class TestBookThenCancelSignedFlow:
    def test_fresher_book_then_admin_cancel_signed_txns(self, session, admin_token, fresher, pro):
        # Insert a slot directly (skip gmail-verified gate)
        slot_id = _insert_interview_slot(pro["user"]["id"])
        # Book as student
        r_book = session.post(
            f"{API}/interviews/book",
            headers=auth_headers(fresher["token"]),
            json={"slot_id": slot_id},
        )
        assert r_book.status_code == 200, r_book.text

        # Find the booking id
        d = _db()
        booking = d.interview_bookings.find_one({"slot_id": slot_id})
        assert booking, "booking record was not created"
        booking_id = booking["id"]

        # Admin cancels with refund=True
        r_cancel = session.post(
            f"{API}/admin/interviews/bookings/{booking_id}/cancel",
            headers=auth_headers(admin_token),
            json={"reason": "iter52 test cancel", "refund": True},
        )
        assert r_cancel.status_code == 200, r_cancel.text
        assert r_cancel.json().get("refund") == 99

        # Now search admin transactions for this user (q matches on email)
        r_search = session.get(
            f"{API}/admin/transactions/search",
            headers=auth_headers(admin_token),
            params={"q": fresher["email"], "limit": 100},
        )
        assert r_search.status_code == 200, r_search.text
        rows = r_search.json()
        # Filter to this user's rows only (defensive)
        my_rows = [x for x in rows if x.get("user_id") == fresher["user"]["id"]]
        booking_row = next((x for x in my_rows if x.get("reason") == "interview_booking"), None)
        refund_row = next((x for x in my_rows if x.get("reason") == "interview_admin_refund"), None)
        assert booking_row, f"No interview_booking row found for user, rows={rows}"
        assert refund_row, f"No interview_admin_refund row found for user, rows={rows}"

        # Signed amounts must be correct
        assert booking_row["amount"] == -99, f"expected -99 got {booking_row['amount']}"
        assert booking_row["credits_deducted"] == 99
        assert booking_row["credits_added"] == 0

        assert refund_row["amount"] == 99, f"expected +99 got {refund_row['amount']}"
        assert refund_row["credits_added"] == 99
        assert refund_row["credits_deducted"] == 0


# ============================================================
# 5) Regression: /api/wallet still returns raw `delta`
# ============================================================
class TestWalletRegression:
    def test_wallet_returns_delta_field(self, session, fresher, admin_token):
        # Seed a slot + book so we have at least one txn on the wallet
        slot_id = _insert_interview_slot(
            _signup_verify(session, "professional", prefix="TEST_I52_PRO_W")["user"]["id"],
            hours_ahead=48,
        )
        # We need pro gmail_verified so booking side effects don't blow up
        # (booking itself only requires slot.available, not pro gmail_verified).
        session.post(
            f"{API}/interviews/book",
            headers=auth_headers(fresher["token"]),
            json={"slot_id": slot_id},
        )
        r = session.get(f"{API}/wallet", headers=auth_headers(fresher["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        txs = data.get("transactions", [])
        assert isinstance(txs, list) and len(txs) > 0
        # Every txn should carry `delta` field (raw doc, untouched by iter52 fix)
        for t in txs:
            assert "delta" in t, f"Wallet txn missing delta: {t}"
            assert isinstance(t["delta"], int)
        # And at least one should be non-zero (the interview_booking we just did)
        assert any(t["delta"] != 0 for t in txs), "All wallet delta values are zero"
