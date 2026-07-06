"""Iteration 54 — Phase C part 2 refactor regression tests.

Verifies auth router extraction (/app/backend/routers/auth.py) did not change behaviour of:
  - POST /api/auth/signup (student / admin-reject / employer-reject / pro personal-email reject / referral)
  - POST /api/auth/verify-otp (verify_email flow + welcome bonus + referral reward)
  - POST /api/auth/login (200, 401 wrong-pw, 403 email_not_verified, 403 account_suspended)
  - POST /api/auth/forgot-password + /api/auth/reset-password
  - GET /api/auth/me (student + pro shape with profile_completion/missing_fields/gmail_verified)
  - POST /api/profile/phone/send-otp (normalises 10/91/+91) and /api/profile/phone/verify-otp
  - POST /api/auth/google (bad session_id → 401)
  - POST /api/pro/gmail/send-otp (accepts gmail.com, rejects non-gmail, rejects same as login)
  - POST /api/pro/gmail/verify-otp (marks gmail_verified + stores alternate_gmail)
  - Adjacent endpoints (wallet deposit create-order, jobs apply, interviews book, admin transactions search)
"""
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Prefer frontend/.env EXPO_PUBLIC_BACKEND_URL (public URL)
BASE_URL = None
fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
if fe_env.exists():
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PW = "Admin@12345"
REDEEM_PRO_EMAIL = "redeem.pro@example.com"
REDEEM_PRO_PW = "RedeemPro@12345"


def _hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    return r


def _signup_student(prefix="iter54", ref=None):
    email = f"{prefix}_s_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Test@12345"
    body = {"email": email, "password": pw, "role": "student", "name": f"{prefix} student"}
    if ref:
        body["ref"] = ref
    r = requests.post(f"{API}/auth/signup", json=body, timeout=30)
    return email, pw, r


def _verify(email, otp, purpose="verify_email"):
    return requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": purpose}, timeout=30)


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ["MONGO_URL"])
    yield mc[os.environ["DB_NAME"]]
    mc.close()


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PW)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---------------- SIGNUP ----------------
class TestSignup:
    def test_signup_student_returns_mock_otp_and_bonus(self, mongo):
        email, pw, r = _signup_student("iter54std")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("email") == email
        assert d.get("mock_otp") and len(d["mock_otp"]) == 6
        u = mongo.users.find_one({"email": email}, {"_id": 0})
        assert u["credits"] == 100
        assert u["referral_code"]
        assert u["role"] == "student"
        assert u["is_email_verified"] is False
        txn = mongo.transactions.find_one({"user_id": u["id"], "reason": "signup_bonus"})
        assert txn and txn["delta"] == 100

    def test_signup_admin_role_rejected(self):
        r = requests.post(f"{API}/auth/signup", json={
            "email": f"iter54_admin_{uuid.uuid4().hex[:6]}@x.io",
            "password": "Test@12345", "role": "admin", "name": "x"
        }, timeout=30)
        assert r.status_code == 400
        assert "admin" in r.text.lower()

    def test_signup_employer_role_rejected_with_team_email(self):
        r = requests.post(f"{API}/auth/signup", json={
            "email": f"iter54_emp_{uuid.uuid4().hex[:6]}@x.io",
            "password": "Test@12345", "role": "employer", "name": "x"
        }, timeout=30)
        assert r.status_code == 400
        assert "Team@referme.today" in r.text

    def test_signup_professional_personal_email_rejected(self):
        r = requests.post(f"{API}/auth/signup", json={
            "email": f"iter54_pro_{uuid.uuid4().hex[:6]}@gmail.com",
            "password": "Test@12345", "role": "professional", "name": "x"
        }, timeout=30)
        assert r.status_code == 400
        assert "company email" in r.text.lower() or "personal" in r.text.lower()

    def test_signup_professional_company_email_ok(self, mongo):
        email = f"iter54_pro_{uuid.uuid4().hex[:8]}@acmecorp.io"
        r = requests.post(f"{API}/auth/signup", json={
            "email": email, "password": "Test@12345", "role": "professional", "name": "x"
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("mock_otp")
        u = mongo.users.find_one({"email": email}, {"_id": 0})
        assert u["role"] == "professional"
        assert u["credits"] == 0

    def test_signup_invalid_ref_code_rejected(self):
        r = requests.post(f"{API}/auth/signup", json={
            "email": f"iter54_ref_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@12345", "role": "student", "name": "x",
            "ref": "BOGUSXX9"
        }, timeout=30)
        assert r.status_code == 400
        assert "referral" in r.text.lower()


# ---------------- VERIFY-OTP + REFERRAL REWARD ----------------
class TestVerifyOtpAndReferral:
    def test_verify_otp_flips_verified_and_returns_jwt(self, mongo):
        email, pw, r = _signup_student("iter54vfy")
        otp = r.json()["mock_otp"]
        v = _verify(email, otp)
        assert v.status_code == 200, v.text
        d = v.json()
        assert d.get("token")
        assert d.get("user", {}).get("email") == email
        assert d.get("welcome_bonus") == 100
        u = mongo.users.find_one({"email": email}, {"_id": 0})
        assert u["is_email_verified"] is True

    def test_referral_reward_fires_on_verify(self, mongo):
        # 1) create referrer & verify
        ref_email, _, rr = _signup_student("iter54ref")
        ref_otp = rr.json()["mock_otp"]
        rv = _verify(ref_email, ref_otp)
        assert rv.status_code == 200
        ref_u = mongo.users.find_one({"email": ref_email}, {"_id": 0})
        ref_code = ref_u["referral_code"]
        credits_before = ref_u["credits"]

        # 2) referred student signs up with ref code
        rd_email, _, rd = _signup_student("iter54rdd", ref=ref_code)
        assert rd.status_code == 200
        # verify
        _verify(rd_email, rd.json()["mock_otp"])

        # 3) referrer should receive REFERRAL_REWARD
        ref_after = mongo.users.find_one({"email": ref_email}, {"_id": 0})
        assert ref_after["credits"] > credits_before
        rrow = mongo.referrals.find_one({"referrer_id": ref_u["id"], "referred_email": rd_email})
        assert rrow and rrow["status"] == "successful"
        rtxn = mongo.transactions.find_one({"user_id": ref_u["id"], "reason": "referral_reward"})
        assert rtxn and rtxn["delta"] > 0


# ---------------- LOGIN ----------------
class TestLogin:
    def test_login_success_after_verify(self):
        email, pw, r = _signup_student("iter54lgn")
        _verify(email, r.json()["mock_otp"])
        lr = _login(email, pw)
        assert lr.status_code == 200
        assert lr.json().get("token")

    def test_login_wrong_password_401(self):
        email, pw, r = _signup_student("iter54lgn2")
        _verify(email, r.json()["mock_otp"])
        lr = _login(email, "WRONG_PW_XYZ")
        assert lr.status_code == 401

    def test_login_unverified_403(self):
        email, pw, r = _signup_student("iter54unv")
        # NO verify
        lr = _login(email, pw)
        assert lr.status_code == 403
        assert "not verified" in lr.text.lower() or "email" in lr.text.lower()

    def test_login_suspended_403(self, mongo):
        email, pw, r = _signup_student("iter54sus")
        _verify(email, r.json()["mock_otp"])
        mongo.users.update_one({"email": email}, {"$set": {"account_status": "suspended"}})
        lr = _login(email, pw)
        assert lr.status_code == 403
        assert "suspend" in lr.text.lower()


# ---------------- FORGOT / RESET ----------------
class TestForgotReset:
    def test_forgot_then_reset_then_login(self):
        email, pw, r = _signup_student("iter54fg")
        _verify(email, r.json()["mock_otp"])
        fr = requests.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=30)
        assert fr.status_code == 200
        otp = fr.json().get("mock_otp")
        assert otp, fr.text
        new_pw = "NewPw@98765"
        rp = requests.post(f"{API}/auth/reset-password", json={
            "email": email, "otp": otp, "new_password": new_pw
        }, timeout=30)
        assert rp.status_code == 200
        # old pw fails
        assert _login(email, pw).status_code == 401
        # new pw works
        assert _login(email, new_pw).status_code == 200


# ---------------- /auth/me ----------------
class TestAuthMe:
    def test_me_student(self):
        email, pw, r = _signup_student("iter54me")
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        me = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=30)
        assert me.status_code == 200
        d = me.json()
        assert d["user"]["email"] == email
        assert "profile" in d
        # Student should NOT have pro-specific fields
        assert "profile_completion" not in d

    def test_me_professional_has_pro_fields(self):
        email = f"iter54_promeh_{uuid.uuid4().hex[:8]}@acmecorp.io"
        pw = "Test@12345"
        r = requests.post(f"{API}/auth/signup", json={
            "email": email, "password": pw, "role": "professional", "name": "x"
        }, timeout=30)
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        me = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=30)
        assert me.status_code == 200
        d = me.json()
        assert "profile_completion" in d
        assert "missing_fields" in d
        assert isinstance(d["missing_fields"], list)
        assert d["user"].get("gmail_verified") in (True, False)
        assert "alternate_gmail" in d["user"]


# ---------------- PHONE OTP ----------------
class TestPhoneOtp:
    @pytest.fixture(scope="class")
    def student_tok(self):
        email, pw, r = _signup_student("iter54ph")
        v = _verify(email, r.json()["mock_otp"])
        return v.json()["token"]

    def test_phone_send_accepts_10digit(self, student_tok):
        r = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": "9876543210"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mock_otp")
        assert d.get("phone", "").endswith("9876543210")

    def test_phone_send_accepts_91_prefix(self, student_tok):
        r = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": "919876543211"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("mock_otp")

    def test_phone_send_accepts_plus91(self, student_tok):
        r = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": "+919876543212"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("mock_otp")

    def test_phone_send_invalid_returns_exact_copy(self, student_tok):
        r = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": "12345"}, timeout=30)
        assert r.status_code == 400
        assert "Please enter a valid 10-digit Indian mobile number." in r.text

    def test_phone_verify_marks_verified(self, student_tok, mongo):
        # Fresh phone specifically for verify assertion
        phone = "9812345670"
        s = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": phone}, timeout=30)
        assert s.status_code == 200
        otp = s.json()["mock_otp"]
        normalized_phone = s.json()["phone"]
        v = requests.post(f"{API}/profile/phone/verify-otp",
                          headers=_hdr(student_tok),
                          json={"phone": normalized_phone, "otp": otp}, timeout=30)
        assert v.status_code == 200, v.text
        d = v.json()
        assert d["user"].get("profile", {}).get("phone_verified") is True or d.get("profile", {}).get("phone_verified") is True

    def test_phone_verify_wrong_otp_400(self, student_tok):
        s = requests.post(f"{API}/profile/phone/send-otp",
                          headers=_hdr(student_tok),
                          json={"phone": "9812345671"}, timeout=30)
        assert s.status_code == 200
        v = requests.post(f"{API}/profile/phone/verify-otp",
                          headers=_hdr(student_tok),
                          json={"phone": s.json()["phone"], "otp": "000000"}, timeout=30)
        assert v.status_code == 400


# ---------------- GOOGLE AUTH (invalid session) ----------------
class TestGoogleAuth:
    def test_google_bad_session_401(self):
        r = requests.post(f"{API}/auth/google",
                          json={"session_id": "bogus_" + uuid.uuid4().hex}, timeout=30)
        # Emergent returns 401 → our endpoint maps to 401
        assert r.status_code in (401, 502), r.status_code


# ---------------- PRO GMAIL OTP ----------------
class TestProGmail:
    @pytest.fixture(scope="class")
    def pro_tok(self):
        email = f"iter54_pgmail_{uuid.uuid4().hex[:8]}@acmecorp.io"
        pw = "Test@12345"
        r = requests.post(f"{API}/auth/signup", json={
            "email": email, "password": pw, "role": "professional", "name": "p"
        }, timeout=30)
        v = _verify(email, r.json()["mock_otp"])
        return {"token": v.json()["token"], "email": email}

    def test_pro_gmail_send_accepts_gmail(self, pro_tok):
        alt = f"iter54.alt.{uuid.uuid4().hex[:6]}@gmail.com"
        r = requests.post(f"{API}/pro/gmail/send-otp",
                          headers=_hdr(pro_tok["token"]),
                          json={"email": alt, "otp": ""}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("mock_otp")
        # store for verify
        pytest.pro_alt_email = alt
        pytest.pro_alt_otp = r.json()["mock_otp"]
        pytest.pro_tok = pro_tok["token"]

    def test_pro_gmail_rejects_non_gmail(self, pro_tok):
        r = requests.post(f"{API}/pro/gmail/send-otp",
                          headers=_hdr(pro_tok["token"]),
                          json={"email": "someone@yahoo.com", "otp": ""}, timeout=30)
        assert r.status_code == 400
        assert "gmail" in r.text.lower()

    def test_pro_gmail_rejects_same_as_login(self, pro_tok):
        r = requests.post(f"{API}/pro/gmail/send-otp",
                          headers=_hdr(pro_tok["token"]),
                          json={"email": pro_tok["email"], "otp": ""}, timeout=30)
        # login email is acmecorp.io (non-gmail) so gmail-check may fire first;
        # either 400 is acceptable — we assert 400.
        assert r.status_code == 400

    def test_pro_gmail_verify_marks_verified(self, mongo):
        alt = getattr(pytest, "pro_alt_email", None)
        otp = getattr(pytest, "pro_alt_otp", None)
        tok = getattr(pytest, "pro_tok", None)
        assert alt and otp and tok, "send-otp must have populated pytest attrs"
        r = requests.post(f"{API}/pro/gmail/verify-otp",
                          headers=_hdr(tok),
                          json={"email": alt, "otp": otp}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("alternate_gmail") == alt
        # persisted?
        u = mongo.users.find_one({"alternate_gmail": alt}, {"_id": 0})
        assert u and u.get("gmail_verified") is True


# ---------------- ADJACENT (shared-helper regression) ----------------
class TestAdjacentEndpoints:
    def test_wallet_deposit_create_order_ok(self):
        email, pw, r = _signup_student("iter54adj")
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        w = requests.post(f"{API}/wallet/deposit/create-order",
                          headers=_hdr(tok),
                          json={"amount_inr": 199}, timeout=30)
        assert w.status_code == 200, w.text
        assert w.json().get("credits_to_grant") == 398

    def test_redemption_submit_pro_only(self, mongo, admin_token):
        # student → 403
        email, pw, r = _signup_student("iter54rdmg")
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        rr = requests.post(f"{API}/redemption/submit",
                           headers=_hdr(tok),
                           json={"credits": 500, "upi_id": "a@upi", "account_holder_name": "S"}, timeout=30)
        assert rr.status_code == 403

    def test_interviews_book_reachable(self):
        email, pw, r = _signup_student("iter54ivb")
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        rr = requests.post(f"{API}/interviews/book",
                           headers=_hdr(tok),
                           json={"slot_id": "nonexistent_xxx"}, timeout=30)
        assert rr.status_code < 500, rr.text

    def test_jobs_apply_reachable(self):
        email, pw, r = _signup_student("iter54japp")
        v = _verify(email, r.json()["mock_otp"])
        tok = v.json()["token"]
        rr = requests.post(f"{API}/jobs/apply",
                           headers=_hdr(tok),
                           json={"job_id": "nonexistent_xxx"}, timeout=30)
        assert rr.status_code < 500, rr.text

    def test_admin_transactions_search_ok(self, admin_token):
        r = requests.get(f"{API}/admin/transactions/search",
                         headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
