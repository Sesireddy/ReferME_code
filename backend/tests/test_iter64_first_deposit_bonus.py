"""Iteration 64 — First Wallet Deposit Bonus tests.

Feature: First-ever successful deposit AND amount_inr ≥ ₹200 → 50% bonus credits
(capped at 5000). Bonus recorded as separate transaction with
reason='first_deposit_bonus'. Subsequent deposits are 1:1 with no bonus.
First deposit < ₹200 → 400.

Also verifies:
- /api/subscription/plans returns is_first_deposit, first_deposit_inr(200),
  first_deposit_bonus_percent(50), first_deposit_bonus_max_credits(5000).
- Referral reward still fires alongside first deposit bonus.
- Regression: /api/wallet, /api/redemption/my still shape-stable.
- deposit_orders collection stores base_credits + bonus_credits and
  credits_to_grant = base + bonus.
"""
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    or os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
)
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

API = f"{BASE_URL}/api"

FIRST_MIN = 200
BONUS_PCT = 50
BONUS_CAP = 5000
REFERRAL_REWARD = 25
STUDENT_WELCOME = 100  # baseline credits on email verify


# ---------------- helpers ----------------
def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _signup(role="student", ref=None, prefix="iter64", domain=None):
    if role == "professional":
        email = f"{prefix}_pro_{uuid.uuid4().hex[:8]}@{domain or 'acmecorp.io'}"
    else:
        email = f"{prefix}_stu_{uuid.uuid4().hex[:8]}@example.com"
    body = {"email": email, "password": "Passw0rd!", "role": role, "name": f"Test {role}"}
    if ref:
        body["ref"] = ref
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    return r, email


def _verify(email, otp):
    return requests.post(
        f"{API}/auth/verify-otp",
        json={"email": email, "otp": otp, "purpose": "verify_email"},
        timeout=30,
    )


def _fresh_student(ref=None):
    """Returns (email, token, user_id)."""
    r, email = _signup(role="student", ref=ref)
    assert r.status_code == 200, f"signup: {r.status_code} {r.text}"
    otp = r.json().get("mock_otp")
    assert otp, "mock_otp missing"
    vr = _verify(email, otp)
    assert vr.status_code == 200, vr.text
    j = vr.json()
    return email, j["token"], j["user"]["id"]


def _wallet(token):
    r = requests.get(f"{API}/wallet", headers=_hdr(token), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_order(token, amount_inr):
    return requests.post(
        f"{API}/wallet/deposit/create-order",
        headers=_hdr(token),
        json={"amount_inr": amount_inr},
        timeout=30,
    )


def _confirm_order(token, order):
    return requests.post(
        f"{API}/wallet/deposit/confirm",
        headers=_hdr(token),
        json={
            "razorpay_order_id": order["razorpay_order_id"],
            "razorpay_payment_id": f"pay_mock_{uuid.uuid4().hex[:12]}",
            "razorpay_signature": "mock_sig",
        },
        timeout=30,
    )


def _do_deposit(token, amount_inr):
    """Full create + confirm; returns (order_json, confirm_json)."""
    co = _create_order(token, amount_inr)
    assert co.status_code == 200, f"create-order failed: {co.status_code} {co.text}"
    order = co.json()
    cf = _confirm_order(token, order)
    assert cf.status_code == 200, f"confirm failed: {cf.status_code} {cf.text}"
    return order, cf.json()


def _mongo_db():
    mc = MongoClient(os.environ["MONGO_URL"])
    return mc, mc[os.environ["DB_NAME"]]


# ---------------- Health ----------------
def test_health_mock_payments_on():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("mock_payments") is True


# ---------------- /api/subscription/plans ----------------
class TestSubscriptionPlansShape:
    def test_plans_paid_tier_contains_new_constants(self):
        _, token, _ = _fresh_student()
        r = requests.get(f"{API}/subscription/plans", headers=_hdr(token), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "free_tier" in j and "paid_tier" in j
        pt = j["paid_tier"]
        assert pt.get("is_first_deposit") is True, f"fresh student should be first_deposit: {pt}"
        assert pt.get("first_deposit_inr") == FIRST_MIN
        assert pt.get("first_deposit_bonus_percent") == BONUS_PCT
        assert pt.get("first_deposit_bonus_max_credits") == BONUS_CAP
        assert isinstance(pt.get("action_cost"), int)

    def test_plans_is_first_deposit_flips_after_deposit(self):
        _, token, _ = _fresh_student()
        _do_deposit(token, 200)
        r = requests.get(f"{API}/subscription/plans", headers=_hdr(token), timeout=30)
        assert r.status_code == 200
        assert r.json()["paid_tier"]["is_first_deposit"] is False


# ---------------- Case 1-3: Bonus math ----------------
class TestFirstDepositBonusMath:
    def test_first_deposit_200_bonus_100(self):
        _, token, uid = _fresh_student()
        pre_credits = _wallet(token)["credits"]  # should be 100 welcome
        order, conf = _do_deposit(token, 200)
        # create-order response fields
        assert order["amount_inr"] == 200
        assert order["base_credits"] == 200
        assert order["bonus_credits"] == 100
        assert order["credits_to_grant"] == 300
        assert order["is_first_deposit"] is True
        # confirm response fields
        assert conf["base_credits"] == 200
        assert conf["bonus_credits"] == 100
        assert conf["added"] == 300
        assert conf["first_deposit_bonus_applied"] is True
        assert conf["credits"] == pre_credits + 300
        # Two transaction rows for this order (deposit + first_deposit_bonus)
        w = _wallet(token)
        deps = [t for t in w["transactions"] if t.get("reason") == "deposit"]
        bonuses = [t for t in w["transactions"] if t.get("reason") == "first_deposit_bonus"]
        assert len(deps) == 1 and deps[0]["delta"] == 200
        assert deps[0].get("meta", {}).get("label") == "Top up"
        assert len(bonuses) == 1 and bonuses[0]["delta"] == 100
        assert bonuses[0].get("meta", {}).get("label") == "First Deposit Bonus (50%)"

    def test_first_deposit_1000_bonus_500(self):
        _, token, _ = _fresh_student()
        pre = _wallet(token)["credits"]
        order, conf = _do_deposit(token, 1000)
        assert order["base_credits"] == 1000
        assert order["bonus_credits"] == 500
        assert order["credits_to_grant"] == 1500
        assert conf["added"] == 1500
        assert conf["first_deposit_bonus_applied"] is True
        assert conf["credits"] == pre + 1500

    def test_first_deposit_15000_bonus_capped_5000(self):
        _, token, _ = _fresh_student()
        pre = _wallet(token)["credits"]
        order, conf = _do_deposit(token, 15000)
        assert order["base_credits"] == 15000
        assert order["bonus_credits"] == BONUS_CAP  # capped
        assert order["credits_to_grant"] == 15000 + BONUS_CAP
        assert conf["added"] == 15000 + BONUS_CAP
        assert conf["first_deposit_bonus_applied"] is True
        assert conf["credits"] == pre + 15000 + BONUS_CAP


# ---------------- Case 4: below min ----------------
class TestBelowMinRejected:
    def test_first_deposit_199_rejected_400(self):
        _, token, _ = _fresh_student()
        r = _create_order(token, 199)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"
        # Message should mention 200
        assert "200" in r.text, r.text

    def test_first_deposit_1_rejected_400(self):
        _, token, _ = _fresh_student()
        r = _create_order(token, 1)
        assert r.status_code == 400


# ---------------- Case 5: second deposit ----------------
class TestSecondDepositNoBonus:
    def test_second_deposit_no_bonus_and_no_bonus_tx(self):
        _, token, uid = _fresh_student()
        # first deposit ₹200
        o1, c1 = _do_deposit(token, 200)
        assert c1["first_deposit_bonus_applied"] is True
        # second deposit ₹500 (arbitrary, ≥ 1; no min for subsequent)
        o2 = _create_order(token, 500)
        assert o2.status_code == 200, o2.text
        oj2 = o2.json()
        assert oj2["is_first_deposit"] is False
        assert oj2["base_credits"] == 500
        assert oj2["bonus_credits"] == 0
        assert oj2["credits_to_grant"] == 500
        cf2 = _confirm_order(token, oj2)
        assert cf2.status_code == 200, cf2.text
        j2 = cf2.json()
        assert j2["base_credits"] == 500
        assert j2["bonus_credits"] == 0
        assert j2["added"] == 500
        assert j2["first_deposit_bonus_applied"] is False
        # No new first_deposit_bonus tx from the second deposit — still exactly 1 bonus tx
        w = _wallet(token)
        bonuses = [t for t in w["transactions"] if t.get("reason") == "first_deposit_bonus"]
        assert len(bonuses) == 1, f"expected exactly 1 bonus tx (from first deposit), got {len(bonuses)}"
        # And two deposit txns
        deps = [t for t in w["transactions"] if t.get("reason") == "deposit"]
        assert len(deps) == 2, f"expected 2 deposit txs, got {len(deps)}: {deps}"
        deltas = sorted(d["delta"] for d in deps)
        assert deltas == [200, 500]


# ---------------- Case 7: Referral + first deposit bonus ----------------
class TestReferralPlusFirstDepositBonus:
    def test_referrer_gets_reward_and_depositor_gets_bonus(self):
        # referrer
        _, r_token, _ = _fresh_student()
        rme = requests.get(f"{API}/refer/me", headers=_hdr(r_token), timeout=15)
        assert rme.status_code == 200
        code = rme.json()["code"]
        r_baseline = _wallet(r_token)["credits"]
        # referred fresh student
        _, d_token, _ = _fresh_student(ref=code)
        d_pre = _wallet(d_token)["credits"]
        order, conf = _do_deposit(d_token, 200)
        # depositor: base+bonus applied
        assert conf["base_credits"] == 200
        assert conf["bonus_credits"] == 100
        assert conf["added"] == 300
        assert conf["first_deposit_bonus_applied"] is True
        assert conf["referral_awarded"] is True
        assert conf["credits"] == d_pre + 300
        # referrer +REFERRAL_REWARD
        r_post = _wallet(r_token)["credits"]
        assert r_post == r_baseline + REFERRAL_REWARD, (
            f"referrer credits {r_baseline} → {r_post}, expected +{REFERRAL_REWARD}"
        )


# ---------------- Deposit orders collection integrity ----------------
class TestDepositOrdersCollection:
    def test_order_row_has_base_bonus_and_total(self):
        _, token, uid = _fresh_student()
        order, _ = _do_deposit(token, 500)
        # order["order_id"] is internal id
        mc, db = _mongo_db()
        try:
            doc = db.deposit_orders.find_one(
                {"razorpay_order_id": order["razorpay_order_id"]}, {"_id": 0}
            )
            assert doc is not None, "order not persisted"
            assert doc.get("base_credits") == 500
            assert doc.get("bonus_credits") == 250
            assert doc.get("credits_to_grant") == 750
            assert doc.get("credits_to_grant") == doc["base_credits"] + doc["bonus_credits"]
            assert doc.get("is_first_deposit") is True
            assert doc.get("status") == "paid"
        finally:
            mc.close()


# ---------------- Regression: existing wallet endpoints ----------------
class TestRegressionWallet:
    def test_wallet_shape(self):
        _, token, _ = _fresh_student()
        w = _wallet(token)
        for k in ("credits", "locked_credits", "free_uses_left", "total_deposits", "action_cost", "transactions"):
            assert k in w, f"missing {k}"
        assert isinstance(w["transactions"], list)

    def test_redemption_my_student_403(self):
        _, token, _ = _fresh_student()
        r = requests.get(f"{API}/redemption/my", headers=_hdr(token), timeout=15)
        # Students are not professionals — role gate should reject
        assert r.status_code == 403, f"expected 403, got {r.status_code}"

    def test_redemption_submit_student_403(self):
        _, token, _ = _fresh_student()
        r = requests.post(
            f"{API}/redemption/submit",
            headers=_hdr(token),
            json={"credits": 500, "upi_id": "x@upi", "account_holder_name": "X"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_redemption_my_pro_shape(self):
        # Use seeded redeem.pro
        lr = requests.post(
            f"{API}/auth/login",
            json={"email": "redeem.pro@example.com", "password": "RedeemPro@12345"},
            timeout=15,
        )
        if lr.status_code != 200:
            pytest.skip(f"redeem.pro seed missing: {lr.status_code}")
        pro_token = lr.json()["token"]
        r = requests.get(f"{API}/redemption/my", headers=_hdr(pro_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        assert d.get("min_credits") == 500
        assert d.get("inr_per_credit") == 1.0
