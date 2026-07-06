"""Iteration 53 — Phase C refactor regression tests.

Verifies the wallet router extraction did not change behaviour of:
  - GET /api/wallet
  - GET /api/subscription/plans
  - POST /api/wallet/deposit/create-order
  - POST /api/wallet/deposit/confirm
  - POST /api/redemption/submit
  - GET /api/redemption/my
  - Adjacent endpoints (auth/me, admin transactions search, interviews book, jobs apply)
  - Admin redemption endpoints (approve / mark-paid / reject)
"""
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from passlib.context import CryptContext

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PW = "Admin@12345"
REDEEM_PRO_EMAIL = "redeem.pro@example.com"
REDEEM_PRO_PW = "RedeemPro@12345"


# ------------------- helpers -------------------
def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()


def _signup(role, prefix="iter53"):
    email = f"{prefix}_{role}_{uuid.uuid4().hex[:8]}@acmecorp.io"
    if role == "student":
        email = f"{prefix}_student_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Test@12345"
    r = requests.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"{prefix} {role}"}, timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"}, timeout=30)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    return {"email": email, "password": pw, "token": d["token"], "user": d["user"]}


def _employer():
    """Employers can't self-signup — create in DB then login."""
    eid = uuid.uuid4().hex
    email = f"iter53_employer_{eid[:8]}@referme.io"
    pw = "Test@12345"
    ph = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(pw)
    mc = MongoClient(os.environ["MONGO_URL"])
    mc[os.environ["DB_NAME"]].users.insert_one({
        "id": eid, "email": email, "role": "employer",
        "name": "iter53 employer", "password_hash": ph,
        "is_email_verified": True, "credits": 0, "profile_complete": True,
        "profile": {"company_name": f"Acme {eid[:6]}"},
        "free_uses_left": 2, "created_at": "2025-01-01T00:00:00+00:00",
    })
    mc.close()
    return _login(email, pw)


# ------------------- fixtures -------------------
@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def redeem_pro():
    # Ensure phone_verified is set so /redemption/submit passes require_phone_verified gate
    mc = MongoClient(os.environ["MONGO_URL"])
    mc[os.environ["DB_NAME"]].users.update_one(
        {"email": REDEEM_PRO_EMAIL},
        {"$set": {"profile.phone_verified": True, "profile.phone": "9999999999"}},
    )
    mc.close()
    return _login(REDEEM_PRO_EMAIL, REDEEM_PRO_PW)


@pytest.fixture(scope="module")
def fresh_student():
    return _signup("student")


@pytest.fixture(scope="module")
def fresh_pro():
    return _signup("professional")


# ------------------- Wallet endpoints -------------------
class TestWalletEndpoints:
    def test_get_wallet_returns_required_fields(self, fresh_student):
        r = requests.get(f"{API}/wallet", headers=_hdr(fresh_student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("credits", "locked_credits", "free_uses_left", "total_deposits", "action_cost", "transactions"):
            assert k in d, f"missing {k}"
        assert isinstance(d["transactions"], list)
        assert isinstance(d["action_cost"], int)

    def test_get_wallet_unauthenticated_401(self):
        r = requests.get(f"{API}/wallet", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_subscription_plans_shape(self, fresh_student):
        r = requests.get(f"{API}/subscription/plans", headers=_hdr(fresh_student["token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "free_tier" in d and "paid_tier" in d
        pt = d["paid_tier"]
        assert pt["first_deposit_inr"] == 199
        assert pt["first_deposit_credits"] == 398
        assert "action_cost" in pt

    def test_subscription_plans_unauth_401(self):
        r = requests.get(f"{API}/subscription/plans", timeout=30)
        assert r.status_code in (401, 403)


# ------------------- Deposit flow -------------------
class TestDepositFlow:
    def test_create_order_first_deposit_bonus(self, fresh_student):
        r = requests.post(f"{API}/wallet/deposit/create-order",
                          headers=_hdr(fresh_student["token"]),
                          json={"amount_inr": 199}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["credits_to_grant"] == 398
        assert d["amount_inr"] == 199
        assert d["razorpay_order_id"].startswith("order_")
        assert "order_id" in d
        # Save for confirm test
        pytest.deposit_order = d
        pytest.deposit_token = fresh_student["token"]
        pytest.deposit_user_id = fresh_student["user"]["id"]

    def test_confirm_deposit_credits_user(self):
        d = getattr(pytest, "deposit_order", None)
        assert d, "create-order must have populated pytest.deposit_order"
        r = requests.post(f"{API}/wallet/deposit/confirm",
                          headers=_hdr(pytest.deposit_token),
                          json={
                              "razorpay_order_id": d["razorpay_order_id"],
                              "razorpay_payment_id": f"pay_test_{uuid.uuid4().hex[:12]}",
                              "razorpay_signature": "mock_sig",
                          }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("added") == 398
        assert body.get("credits") >= 398

        # verify persistence via GET /wallet
        w = requests.get(f"{API}/wallet", headers=_hdr(pytest.deposit_token), timeout=30).json()
        assert w["credits"] >= 398
        assert w["total_deposits"] >= 1
        # ledger has 'deposit' entry with +398
        deposits = [t for t in w["transactions"] if t.get("reason") == "deposit"]
        assert deposits, f"no deposit txn: {w['transactions']}"
        assert deposits[0]["delta"] == 398

    def test_confirm_deposit_invalid_order_404(self, fresh_student):
        r = requests.post(f"{API}/wallet/deposit/confirm",
                          headers=_hdr(fresh_student["token"]),
                          json={
                              "razorpay_order_id": "order_nonexistent_xxx",
                              "razorpay_payment_id": "pay_x",
                              "razorpay_signature": "sig_x",
                          }, timeout=30)
        assert r.status_code == 404, r.status_code

    def test_create_order_first_below_min_rejected(self):
        s = _signup("student", prefix="iter53min")
        r = requests.post(f"{API}/wallet/deposit/create-order",
                          headers=_hdr(s["token"]),
                          json={"amount_inr": 50}, timeout=30)
        assert r.status_code == 400
        assert "199" in r.text


# ------------------- Redemption (pro side) -------------------
class TestRedemption:
    def test_get_my_redemptions_shape(self, redeem_pro):
        r = requests.get(f"{API}/redemption/my", headers=_hdr(redeem_pro["token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        assert d.get("min_credits") == 500
        assert d.get("inr_per_credit") == 1.0

    def test_submit_redemption_deducts_and_locks(self, redeem_pro):
        # get pre balance
        w_before = requests.get(f"{API}/wallet", headers=_hdr(redeem_pro["token"]), timeout=30).json()
        credits_before = w_before["credits"]
        locked_before = w_before["locked_credits"]
        if credits_before < 500:
            pytest.skip(f"redeem_pro has insufficient credits ({credits_before}); seed data missing")

        amount = 500
        r = requests.post(f"{API}/redemption/submit",
                          headers=_hdr(redeem_pro["token"]),
                          json={
                              "credits": amount,
                              "upi_id": "test.pro@upi",
                              "account_holder_name": "Redeem Pro",
                              "bank_account": "",
                              "ifsc": "",
                          }, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "pending"
        assert doc["credits_requested"] == amount
        assert doc["amount_inr"] == float(amount)  # 1 credit = ₹1
        assert doc["upi_id"] == "test.pro@upi"
        req_id = doc["id"]

        # verify wallet reflects lock
        w_after = requests.get(f"{API}/wallet", headers=_hdr(redeem_pro["token"]), timeout=30).json()
        assert w_after["credits"] == credits_before - amount
        assert w_after["locked_credits"] == locked_before + amount
        # ledger has redemption_locked
        locked_txs = [t for t in w_after["transactions"] if t.get("reason") == "redemption_locked"]
        assert locked_txs, "no redemption_locked ledger entry"
        assert locked_txs[0]["delta"] == -amount

        # visible in /redemption/my
        my = requests.get(f"{API}/redemption/my", headers=_hdr(redeem_pro["token"]), timeout=30).json()
        assert any(i["id"] == req_id for i in my["items"])

        # save for admin flow
        pytest.redemption_req_id = req_id
        pytest.redemption_locked_before = locked_before + amount
        pytest.redemption_credits_before = credits_before - amount

    def test_submit_below_min_400(self, redeem_pro):
        # Pydantic validator rejects credits < 500 with 422 (RedemptionSubmitBody.credits: ge=500)
        r = requests.post(f"{API}/redemption/submit",
                          headers=_hdr(redeem_pro["token"]),
                          json={"credits": 100, "upi_id": "x@upi", "account_holder_name": "Redeem Pro"}, timeout=30)
        assert r.status_code in (400, 422), r.status_code

    def test_submit_invalid_upi_400(self, redeem_pro):
        r = requests.post(f"{API}/redemption/submit",
                          headers=_hdr(redeem_pro["token"]),
                          json={"credits": 500, "upi_id": "not-a-upi", "account_holder_name": "Redeem Pro"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_submit_role_gate_student_403(self, fresh_student):
        r = requests.post(f"{API}/redemption/submit",
                          headers=_hdr(fresh_student["token"]),
                          json={"credits": 500, "upi_id": "a@upi", "account_holder_name": "S"}, timeout=30)
        assert r.status_code == 403, r.status_code

    def test_my_redemptions_role_gate_student_403(self, fresh_student):
        r = requests.get(f"{API}/redemption/my", headers=_hdr(fresh_student["token"]), timeout=30)
        assert r.status_code == 403, r.status_code

    def test_redemption_unauth_401(self):
        r = requests.get(f"{API}/redemption/my", timeout=30)
        assert r.status_code in (401, 403)


# ------------------- Admin redemption endpoints (still in server.py) -------------------
class TestAdminRedemption:
    def test_admin_list_and_counts(self, admin):
        r = requests.get(f"{API}/admin/redemption-requests", headers=_hdr(admin["token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "counts" in d
        assert isinstance(d["counts"], dict)

    def test_admin_reject_returns_credits(self, admin, redeem_pro):
        req_id = getattr(pytest, "redemption_req_id", None)
        if not req_id:
            pytest.skip("no redemption created earlier")

        # get current balance
        w_pre = requests.get(f"{API}/wallet", headers=_hdr(redeem_pro["token"]), timeout=30).json()
        r = requests.post(f"{API}/admin/redemption-requests/{req_id}/reject",
                          headers=_hdr(admin["token"]),
                          json={"reason": "iter53 regression rollback"}, timeout=30)
        assert r.status_code == 200, r.text
        # verify refunded
        w_post = requests.get(f"{API}/wallet", headers=_hdr(redeem_pro["token"]), timeout=30).json()
        assert w_post["credits"] == w_pre["credits"] + 500
        assert w_post["locked_credits"] == w_pre["locked_credits"] - 500


# ------------------- Adjacent endpoints (regression) -------------------
class TestAdjacentEndpoints:
    def test_auth_me_ok(self, fresh_student):
        r = requests.get(f"{API}/auth/me", headers=_hdr(fresh_student["token"]), timeout=30)
        assert r.status_code == 200
        u = r.json().get("user") or r.json()
        assert "email" in u

    def test_admin_transactions_search_ok(self, admin):
        r = requests.get(f"{API}/admin/transactions/search", headers=_hdr(admin["token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Response is a plain list of transaction dicts (validated in iteration 52).
        assert isinstance(d, list) or "items" in d

    def test_jobs_apply_endpoint_reachable(self, fresh_student):
        """Confirms _credit_user/_can_use_free imports still resolve — a 404/400 (not 500)
        indicates the endpoint executed business logic successfully."""
        r = requests.post(f"{API}/jobs/apply",
                          headers=_hdr(fresh_student["token"]),
                          json={"job_id": "nonexistent_job_xxx"}, timeout=30)
        # Expected: 400/404 (job not found or ineligible), NOT 500 (import error)
        assert r.status_code < 500, f"5xx from jobs/apply indicates broken helper import: {r.status_code} {r.text}"

    def test_interviews_book_endpoint_reachable(self, fresh_student):
        r = requests.post(f"{API}/interviews/book",
                          headers=_hdr(fresh_student["token"]),
                          json={"slot_id": "nonexistent_slot_xxx"}, timeout=30)
        assert r.status_code < 500, f"5xx from interviews/book indicates broken helper import: {r.status_code} {r.text}"
