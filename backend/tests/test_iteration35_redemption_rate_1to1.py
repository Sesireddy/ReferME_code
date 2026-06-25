"""Iteration 35: Credit redemption rate change verification.

Tests that the redemption rate has been changed from 2 credits = ₹1 (0.5 INR/credit)
to 1 credit = ₹1 (1.0 INR/credit).

Verifies:
- GET /api/redemption/my returns inr_per_credit=1.0 and min_credits=500
- POST /api/redemption/submit with credits=500 → amount_inr=500.0
- POST /api/redemption/submit with credits=1234 → amount_inr=1234.0
- Admin approve + mark-paid notifications reference correct ₹ amount
- Topup rate unchanged: /api/wallet/plans subsequent_rate == "1 INR = 1 credit"
- Topup rate unchanged: deposit amount_inr=199 → 199 credits
- ACTION_COST=49 unchanged (apply deducts 49 credits)
"""
import os
import pytest
from pymongo import MongoClient
from conftest import API, auth_headers, _signup_verify


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _verify_pro_phone(session, token, phone="+919876549999"):
    r = session.post(
        f"{API}/profile/phone/send-otp",
        json={"phone": phone},
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    v = session.post(
        f"{API}/profile/phone/verify-otp",
        json={"phone": phone, "otp": otp},
        headers=auth_headers(token),
    )
    assert v.status_code == 200, v.text


def _give_credits(user_id: str, amount: int):
    _mongo().users.update_one({"id": user_id}, {"$inc": {"credits": amount}})


# ---------- /api/redemption/my ----------
class TestRedemptionMyConstants:
    def test_inr_per_credit_is_1_and_min_500(self, session, professional):
        r = session.get(f"{API}/redemption/my", headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("min_credits") == 500, f"min_credits expected 500, got {body.get('min_credits')}"
        assert body.get("inr_per_credit") == 1.0, f"inr_per_credit expected 1.0, got {body.get('inr_per_credit')}"
        assert "items" in body


# ---------- /api/redemption/submit at 1:1 rate ----------
class TestRedemptionSubmitOneToOne:
    def test_submit_500_credits_returns_500_inr(self, session, professional):
        # Need verified phone + ≥500 credits
        _verify_pro_phone(session, professional["token"], phone="+919876510001")
        _give_credits(professional["user"]["id"], 1500)

        # Wallet baseline
        w0 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        c0 = w0["credits"]
        assert c0 >= 500, f"setup failed; credits={c0}"

        r = session.post(
            f"{API}/redemption/submit",
            json={"credits": 500, "upi_id": "test@upi", "account_holder_name": "TEST Holder"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["credits_requested"] == 500
        assert doc["amount_inr"] == 500.0, f"expected 500.0, got {doc['amount_inr']} (rate regression!)"
        assert doc["status"] == "pending"

        # Wallet debited by 500 (held in locked_credits)
        w1 = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()
        assert w1["credits"] == c0 - 500, f"credits delta wrong: {c0}->{w1['credits']}"
        # locked_credits incremented (may not be returned, check DB)
        user_doc = _mongo().users.find_one({"id": professional["user"]["id"]})
        assert (user_doc.get("locked_credits") or 0) >= 500

    def test_submit_1234_credits_returns_1234_inr(self, session, professional):
        _verify_pro_phone(session, professional["token"], phone="+919876510002")
        _give_credits(professional["user"]["id"], 2000)

        r = session.post(
            f"{API}/redemption/submit",
            json={"credits": 1234, "upi_id": "test@upi", "account_holder_name": "TEST Holder"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["credits_requested"] == 1234
        assert doc["amount_inr"] == 1234.0, f"expected 1234.0, got {doc['amount_inr']}"


# ---------- Admin approve + mark-paid notification references ----------
class TestAdminApproveAndPaidReferences:
    def test_full_lifecycle_notifications_reference_1to1_amount(self, session, professional, admin_token):
        _verify_pro_phone(session, professional["token"], phone="+919876510003")
        _give_credits(professional["user"]["id"], 1000)
        pro_id = professional["user"]["id"]

        # Submit redemption for 500 credits => ₹500
        r = session.post(
            f"{API}/redemption/submit",
            json={"credits": 500, "upi_id": "test@upi", "account_holder_name": "TEST Holder"},
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 200, r.text
        req = r.json()
        req_id = req["id"]
        assert req["amount_inr"] == 500.0

        # Verify the submit notification was created with ₹500
        notes = list(_mongo().notifications.find({"user_id": pro_id}).sort("created_at", -1).limit(5))
        submit_note = next((n for n in notes if "pending approval" in (n.get("body") or "").lower()), None)
        assert submit_note is not None, f"submit notification not found: {[n.get('body') for n in notes]}"
        assert "₹500" in submit_note["body"], f"expected ₹500 in body, got: {submit_note['body']}"
        assert "₹250" not in submit_note["body"], f"old 0.5 rate leaked into notification: {submit_note['body']}"

        # Admin approve
        ra = session.post(
            f"{API}/admin/redemption-requests/{req_id}/approve",
            headers=auth_headers(admin_token),
        )
        assert ra.status_code == 200, ra.text
        approve_note = list(_mongo().notifications.find({"user_id": pro_id}).sort("created_at", -1).limit(3))
        approve_msg = next((n for n in approve_note if "approved" in (n.get("title") or "").lower()), None)
        assert approve_msg is not None
        # Approve note references "500 credits" (no ₹ in approve note text)
        assert "500" in approve_msg["body"]

        # Admin mark paid
        rp = session.post(
            f"{API}/admin/redemption-requests/{req_id}/mark-paid",
            json={"payment_ref": "TXN-1to1-TEST", "remarks": "ok"},
            headers=auth_headers(admin_token),
        )
        assert rp.status_code == 200, rp.text
        paid_notes = list(_mongo().notifications.find({"user_id": pro_id}).sort("created_at", -1).limit(3))
        paid_msg = next((n for n in paid_notes if "paid" in (n.get("title") or "").lower()), None)
        assert paid_msg is not None
        assert "₹500" in paid_msg["body"], f"expected ₹500 in paid body, got: {paid_msg['body']}"
        assert "₹250" not in paid_msg["body"], f"old 0.5 rate leaked: {paid_msg['body']}"

        # DB state: redemption stored with amount_inr=500.0
        doc = _mongo().redemption_requests.find_one({"id": req_id})
        assert doc["status"] == "paid"
        assert doc["amount_inr"] == 500.0
        assert doc["payment_ref"] == "TXN-1to1-TEST"


# ---------- Topup regression: 199 INR -> 199 credits ----------
class TestTopupRegression:
    def test_subscription_plans_subsequent_rate_unchanged(self, session, student):
        # The plans endpoint is /api/subscription/plans (paid_tier.subsequent_rate)
        r = session.get(f"{API}/subscription/plans", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        paid = body.get("paid_tier") or {}
        assert paid.get("subsequent_rate") == "1 INR = 1 credit", (
            f"topup rate string changed: {paid.get('subsequent_rate')}"
        )
        assert paid.get("action_cost") == 49, f"action_cost regressed: {paid.get('action_cost')}"

    def test_first_deposit_199_inr_creates_398_credits_bonus(self, session, student):
        # First-time deposit at exactly ₹199 is a bonus path (₹199 → 398 credits).
        r = session.post(
            f"{API}/wallet/deposit/create-order",
            json={"amount_inr": 199},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("amount_inr") == 199
        # First deposit bonus path: 398 credits
        assert body.get("credits_to_grant") == 398, (
            f"first-deposit credits regressed: {body.get('credits_to_grant')}"
        )

    def test_subsequent_deposit_uses_1_inr_per_credit(self, session, student):
        # Simulate "already deposited" state so the subsequent 1:1 rate applies
        _mongo().users.update_one(
            {"id": student["user"]["id"]},
            {"$set": {"total_deposits": 1}},
        )
        r = session.post(
            f"{API}/wallet/deposit/create-order",
            json={"amount_inr": 250},
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Subsequent rate: 1 INR = 1 credit (so ₹250 -> 250 credits)
        assert body.get("credits_to_grant") == 250, (
            f"subsequent 1:1 topup rate regressed: {body.get('credits_to_grant')}"
        )


# ---------- ACTION_COST unchanged at 49 ----------
class TestActionCostUnchanged:
    def test_apply_deducts_49_credits(self, session, employer, student):
        # Employer posts a job
        job_body = {
            "title": "Iter35 ActionCost Job",
            "company": "EmpCo",
            "description": "test role",
            "location": "Remote",
            "skills_required": ["python"],
            "category": "fresher",
        }
        rj = session.post(f"{API}/jobs", json=job_body, headers=auth_headers(employer["token"]))
        assert rj.status_code == 200, rj.text
        job_id = rj.json()["id"]

        # Give student enough credits + exhaust their free_uses if any
        _give_credits(student["user"]["id"], 200)
        # Burn free uses first by applying to throwaway jobs OR just check delta is 49
        # Apply enough times to ensure we go through a paid apply path
        w0 = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json()["credits"]
        free_uses = session.get(f"{API}/auth/me", headers=auth_headers(student["token"])).json().get("user", {}).get("free_uses_left", 0)

        r = session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        w1 = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json()["credits"]
        delta = w0 - w1
        # If free use was consumed, delta == 0; else delta == 49
        if free_uses and free_uses > 0:
            assert delta in (0, 49), f"unexpected delta when free_uses>0: {delta}"
        else:
            assert delta == 49, f"ACTION_COST regression: expected 49, got {delta}"
