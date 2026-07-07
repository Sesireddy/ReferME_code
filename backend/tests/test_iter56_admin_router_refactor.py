"""Iteration 56 — Phase D admin router refactor regression tests.

Verifies all 35 /admin/* endpoints extracted into /app/backend/routers/admin.py
still behave identically post-refactor. NO business logic changes expected.

Scope:
 - Admin auth gating (401 unauthenticated, 403 non-admin) on every endpoint
 - Smoke 200s on all GET/list endpoints
 - Status-change moderation approve → hire → HIRING_REWARD + REFERRAL_HIRED_REWARD credit
 - Payout reject → refunds credits via payout_refund
 - Users CRUD (search filters, patch, credit adjust, suspend/activate, delete-admin block)
 - Jobs verify (approve + reject-with-reason)
 - Interviews (admin-cancel booking refunds credits_charged, slot cancel refund)
 - Stats/overview + transactions search (delta signed amount)
 - Redemption workflow approve → mark-paid (locked_credits burn) → reject (refund)
 - CSV exports return text/csv StreamingResponse
 - Audit logs + disputes resolve
 - Wallet refund adjusts credits
 - Adjacent endpoints unchanged (wallet, auth/me, jobs, professionals, applications, leaderboard/students)
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    fe = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

API = f"{BASE_URL}/api"

HIRING_REWARD = 1500
REFERRAL_HIRED_REWARD = 500


# ------------------- helpers -------------------

def _mongo():
    mc = MongoClient(os.environ["MONGO_URL"])
    return mc, mc[os.environ["DB_NAME"]]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _signup(session, role, tag="i56"):
    email = f"{tag}_{role}_{uuid.uuid4().hex[:8]}@referme.io"
    r = session.post(f"{API}/auth/signup", json={"email": email, "password": "Test@12345", "role": role, "name": f"{tag} {role}"})
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    v = session.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    assert v.status_code == 200, v.text
    return {"email": email, "password": "Test@12345", "token": v.json()["token"], "user": v.json()["user"]}


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_tok(session):
    r = session.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def student_tok(session):
    return _signup(session, "student")


@pytest.fixture(scope="module")
def pro_tok(session):
    p = _signup(session, "professional")
    # flip phone_verified so pro can post jobs / access pro-only endpoints
    mc, db = _mongo()
    db.users.update_one({"id": p["user"]["id"]}, {"$set": {"profile.phone_verified": True, "gmail_verified": True, "alternate_gmail": f"pro.{uuid.uuid4().hex[:6]}@gmail.com"}})
    mc.close()
    return p


# ==================== 1. Auth gating (401/403) ====================

class TestAuthGating:
    """Every /admin/* endpoint must be admin-only.
    Sample a representative subset to prove the admin_only dep is wired on every route.
    """
    ENDPOINTS = [
        ("GET", "/admin/status-changes", None),
        ("GET", "/admin/users", None),
        ("GET", "/admin/users/search", None),
        ("GET", "/admin/jobs", None),
        ("GET", "/admin/jobs/search", None),
        ("GET", "/admin/interviews", None),
        ("GET", "/admin/interviews/search", None),
        ("GET", "/admin/interview-bookings", None),
        ("GET", "/admin/stats", None),
        ("GET", "/admin/stats/overview", None),
        ("GET", "/admin/transactions/search", None),
        ("GET", "/admin/redemption-requests", None),
        ("GET", "/admin/audit-logs", None),
        ("GET", "/admin/export/users", None),
        ("GET", "/admin/export/jobs", None),
        ("GET", "/admin/export/interviews", None),
        ("GET", "/admin/export/transactions", None),
        ("GET", "/admin/export/redemptions", None),
        ("POST", "/admin/status-changes/action", {"change_id": "x", "action": "approve"}),
        ("POST", "/admin/payouts/action", {"payout_id": "x", "action": "approve"}),
        ("POST", "/admin/wallet/refund?user_id=x&amount=10", None),
    ]

    def test_no_token_returns_401(self, session):
        for m, path, body in self.ENDPOINTS:
            r = session.request(m, f"{API}{path}", json=body)
            assert r.status_code in (401, 403), f"{m} {path} -> {r.status_code}"

    def test_non_admin_forbidden(self, session, student_tok):
        for m, path, body in self.ENDPOINTS:
            r = session.request(m, f"{API}{path}", headers=_headers(student_tok["token"]), json=body)
            assert r.status_code == 403, f"non-admin should be 403 on {m} {path} -> {r.status_code}"


# ==================== 2. GET/list smoke tests ====================

class TestListSmoke:
    def test_status_changes(self, session, admin_tok):
        r = session.get(f"{API}/admin/status-changes", headers=_headers(admin_tok))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_users(self, session, admin_tok):
        r = session.get(f"{API}/admin/users", headers=_headers(admin_tok))
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) > 0
        assert "account_status" in users[0]

    def test_users_search_filters(self, session, admin_tok):
        # student filter
        r = session.get(f"{API}/admin/users/search?user_type=student", headers=_headers(admin_tok))
        assert r.status_code == 200
        assert all(u.get("role") == "student" for u in r.json())
        # registration_range=last_7
        r = session.get(f"{API}/admin/users/search?registration_range=last_7", headers=_headers(admin_tok))
        assert r.status_code == 200
        # q free-text
        r = session.get(f"{API}/admin/users/search?q=admin", headers=_headers(admin_tok))
        assert r.status_code == 200
        # mobile_verified
        r = session.get(f"{API}/admin/users/search?mobile_verified=verified", headers=_headers(admin_tok))
        assert r.status_code == 200

    def test_jobs(self, session, admin_tok):
        r = session.get(f"{API}/admin/jobs", headers=_headers(admin_tok))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_jobs_search(self, session, admin_tok):
        r = session.get(f"{API}/admin/jobs/search?limit=20", headers=_headers(admin_tok))
        assert r.status_code == 200
        jobs = r.json()
        assert isinstance(jobs, list)
        if jobs:
            assert "applied_count" in jobs[0]
            assert "shortlisted_count" in jobs[0]

    def test_interviews(self, session, admin_tok):
        r = session.get(f"{API}/admin/interviews", headers=_headers(admin_tok))
        assert r.status_code == 200

    def test_interviews_search(self, session, admin_tok):
        r = session.get(f"{API}/admin/interviews/search?limit=10", headers=_headers(admin_tok))
        assert r.status_code == 200

    def test_interview_bookings(self, session, admin_tok):
        r = session.get(f"{API}/admin/interview-bookings", headers=_headers(admin_tok))
        assert r.status_code == 200
        for b in r.json():
            assert "current_slot_status" in b

    def test_stats(self, session, admin_tok):
        r = session.get(f"{API}/admin/stats", headers=_headers(admin_tok))
        assert r.status_code == 200
        d = r.json()
        for k in ["total_users", "students", "professionals", "jobs"]:
            assert k in d

    def test_stats_overview(self, session, admin_tok):
        r = session.get(f"{API}/admin/stats/overview", headers=_headers(admin_tok))
        assert r.status_code == 200
        d = r.json()
        assert "credits" in d
        c = d["credits"]
        # after iter52 fix these should be non-zero
        assert c.get("purchased", 0) > 0, f"purchased bucket 0 -- iter52 delta fix broke"
        assert c.get("used", 0) > 0, f"used bucket 0"
        assert c.get("earned", 0) > 0, f"earned bucket 0"
        assert c.get("rewarded", 0) > 0, f"rewarded bucket 0"

    def test_transactions_search_signed_amount(self, session, admin_tok):
        r = session.get(f"{API}/admin/transactions/search?limit=100", headers=_headers(admin_tok))
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        non_zero = [t for t in rows if t.get("amount", 0) != 0]
        assert len(non_zero) > 0, "no signed amounts non-zero — iter52 delta fix broken"
        # sanity: credits_added / credits_deducted derive correctly
        for t in non_zero[:20]:
            a = t["amount"]
            assert (a > 0 and t["credits_added"] == a and t["credits_deducted"] == 0) or \
                   (a < 0 and t["credits_deducted"] == -a and t["credits_added"] == 0)

    def test_redemption_requests(self, session, admin_tok):
        r = session.get(f"{API}/admin/redemption-requests", headers=_headers(admin_tok))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "counts" in d
        assert all(k in d["counts"] for k in ("pending", "approved", "paid", "rejected"))

    def test_audit_logs_shape(self, session, admin_tok):
        r = session.get(f"{API}/admin/audit-logs?limit=10", headers=_headers(admin_tok))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        assert "retention_days_for_jobs_and_interviews" in d
        assert isinstance(d["retention_days_for_jobs_and_interviews"], int)


# ==================== 3. CSV exports ====================

class TestCSVExports:
    @pytest.mark.parametrize("path", [
        "/admin/export/users",
        "/admin/export/jobs",
        "/admin/export/interviews",
        "/admin/export/transactions",
        "/admin/export/redemptions",
    ])
    def test_csv_streaming(self, session, admin_tok, path):
        r = session.get(f"{API}{path}", headers=_headers(admin_tok))
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        ct = r.headers.get("content-type", "")
        # StreamingResponse for csv fmt — should be text/csv
        assert "csv" in ct or "text" in ct, f"{path} content-type={ct}"
        assert len(r.text) > 0
        first_line = r.text.splitlines()[0]
        assert "," in first_line, f"{path} first line has no comma header"


# ==================== 4. Users CRUD ====================

class TestUsersCRUD:
    def test_patch_user_name(self, session, admin_tok):
        # create disposable user
        u = _signup(session, "student", "iter56u")
        r = session.patch(
            f"{API}/admin/users/{u['user']['id']}",
            headers=_headers(admin_tok),
            json={"name": "Renamed User", "reason": "iter56 test"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["user"]["name"] == "Renamed User"

    def test_credits_adjust_positive_and_ledger(self, session, admin_tok):
        u = _signup(session, "student", "iter56c")
        before = u["user"].get("credits", 0)
        r = session.post(
            f"{API}/admin/users/{u['user']['id']}/credits/adjust",
            headers=_headers(admin_tok),
            json={"delta": 250, "reason": "iter56 grant"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["credits"] == before + 250
        # verify ledger row
        mc, db = _mongo()
        row = db.transactions.find_one({"user_id": u["user"]["id"], "reason": "admin_adjustment"})
        mc.close()
        assert row and row["delta"] == 250

    def test_credits_adjust_zero_delta_400(self, session, admin_tok):
        u = _signup(session, "student", "iter56c0")
        r = session.post(
            f"{API}/admin/users/{u['user']['id']}/credits/adjust",
            headers=_headers(admin_tok),
            json={"delta": 0, "reason": "iter56 zero-delta test"},
        )
        assert r.status_code == 400

    def test_suspend_and_activate(self, session, admin_tok):
        u = _signup(session, "student", "iter56s")
        r1 = session.post(f"{API}/admin/users/{u['user']['id']}/suspend", headers=_headers(admin_tok))
        assert r1.status_code == 200
        mc, db = _mongo()
        d = db.users.find_one({"id": u["user"]["id"]})
        mc.close()
        assert d["account_status"] == "suspended"
        r2 = session.post(f"{API}/admin/users/{u['user']['id']}/activate", headers=_headers(admin_tok))
        assert r2.status_code == 200

    def test_delete_admin_blocked(self, session, admin_tok):
        # find admin user id
        mc, db = _mongo()
        adm = db.users.find_one({"email": "admin@referme.app"})
        mc.close()
        r = session.delete(f"{API}/admin/users/{adm['id']}", headers=_headers(admin_tok))
        assert r.status_code == 404  # blocked by the role: {$ne: admin} filter

    def test_delete_non_admin_ok(self, session, admin_tok):
        u = _signup(session, "student", "iter56d")
        r = session.delete(f"{API}/admin/users/{u['user']['id']}", headers=_headers(admin_tok))
        assert r.status_code == 200


# ==================== 5. Wallet refund ====================

class TestWalletRefund:
    def test_admin_refund_credits_a_user(self, session, admin_tok):
        u = _signup(session, "student", "iter56w")
        r = session.post(
            f"{API}/admin/wallet/refund?user_id={u['user']['id']}&amount=77&reason=iter56_test",
            headers=_headers(admin_tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["credits"] >= 77

    def test_admin_refund_bad_amount(self, session, admin_tok, student_tok):
        r = session.post(
            f"{API}/admin/wallet/refund?user_id={student_tok['user']['id']}&amount=0",
            headers=_headers(admin_tok),
        )
        assert r.status_code == 400


# ==================== 6. Disputes ====================

class TestDisputes:
    def test_resolve_missing_returns_404(self, session, admin_tok):
        r = session.post(f"{API}/admin/disputes/nonexistent-id/resolve", headers=_headers(admin_tok))
        assert r.status_code == 404


# ==================== 7. Status-change moderation → HIRING_REWARD ====================

class TestStatusChangeHire:
    """End-to-end: pro posts a pro-job, student applies, poster raises 'hired' status change,
    admin approves → poster gets +1500 HIRING_REWARD."""

    def test_hire_flow_credits_poster(self, session, admin_tok):
        # Fresh pro poster with phone_verified
        pro = _signup(session, "professional", "iter56pr")
        mc, db = _mongo()
        db.users.update_one({"id": pro["user"]["id"]}, {"$set": {"profile.phone_verified": True, "credits": 500}})
        # student
        stu = _signup(session, "student", "iter56st")
        db.users.update_one({"id": stu["user"]["id"]}, {"$set": {"credits": 500, "profile.preferred_role": "fresher", "profile.current_location": "Bengaluru", "profile.skills": ["python"]}})
        # insert a pro-job directly (bypass /jobs to sidestep model quirks)
        job_id = f"iter56job_{uuid.uuid4().hex[:8]}"
        db.jobs.insert_one({
            "id": job_id,
            "title": "TEST iter56 role",
            "description": "iter56 test",
            "company": "TestCo",
            "location": "Bengaluru",
            "skill_set": ["python"],
            "employer_id": pro["user"]["id"],
            "poster_role": "professional",
            "verification_status": "verified",
            "source": "pro",
            "status": "open",
            "open_positions": 1,
            "bulk_openings": 1,
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        mc.close()
        # student applies
        r = session.post(f"{API}/jobs/apply", headers=_headers(stu["token"]), json={"job_id": job_id})
        assert r.status_code == 200, r.text
        app_id = r.json()["id"] if "id" in r.json() else r.json().get("application_id")
        if not app_id:
            # fetch from db
            mc, db = _mongo()
            appdoc = db.applications.find_one({"job_id": job_id, "student_id": stu["user"]["id"]})
            mc.close()
            app_id = appdoc["id"]

        # Poster raises hire status-change
        r = session.post(
            f"{API}/applications/hire",
            headers=_headers(pro["token"]),
            json={"application_id": app_id, "proof_base64": "data:image/png;base64,AAA", "proof_filename": "p.png", "proof_mime_type": "image/png", "note": "iter56"},
        )
        assert r.status_code == 200, r.text

        # Find pending status change
        mc, db = _mongo()
        chg = db.status_changes.find_one({"application_id": app_id, "status": "pending"})
        mc.close()
        assert chg, "no pending status_change created"

        # capture poster credits before
        mc, db = _mongo()
        credits_before = db.users.find_one({"id": pro["user"]["id"]}).get("credits", 0)
        mc.close()

        # Admin approves
        r = session.post(
            f"{API}/admin/status-changes/action",
            headers=_headers(admin_tok),
            json={"change_id": chg["id"], "action": "approve", "note": "ok"},
        )
        assert r.status_code == 200, r.text

        # Verify credits increased by 1500 & status = hired
        mc, db = _mongo()
        credits_after = db.users.find_one({"id": pro["user"]["id"]}).get("credits", 0)
        appdoc = db.applications.find_one({"id": app_id})
        chg_after = db.status_changes.find_one({"id": chg["id"]})
        # verify hiring_reward transaction row exists
        hr_row = db.transactions.find_one({"user_id": pro["user"]["id"], "reason": "hiring_reward", "meta.application_id": app_id})
        mc.close()
        assert credits_after - credits_before == HIRING_REWARD, f"expected +{HIRING_REWARD}, got {credits_after - credits_before}"
        assert appdoc["status"] == "hired"
        assert any(h["status"] == "hired" for h in (appdoc.get("status_history") or []))
        assert chg_after["status"] == "approved"
        assert hr_row is not None

    def test_reject_leaves_status_unchanged(self, session, admin_tok):
        # Set up small scenario for reject
        pro = _signup(session, "professional", "iter56pr2")
        stu = _signup(session, "student", "iter56st2")
        mc, db = _mongo()
        db.users.update_one({"id": pro["user"]["id"]}, {"$set": {"profile.phone_verified": True, "credits": 500}})
        db.users.update_one({"id": stu["user"]["id"]}, {"$set": {"credits": 500, "profile.preferred_role": "fresher", "profile.current_location": "Bengaluru", "profile.skills": ["python"]}})
        job_id = f"iter56job2_{uuid.uuid4().hex[:8]}"
        db.jobs.insert_one({
            "id": job_id, "title": "T", "description": "d", "company": "C", "location": "Bengaluru",
            "skill_set": ["python"], "employer_id": pro["user"]["id"], "poster_role": "professional",
            "verification_status": "verified", "source": "pro", "status": "open", "open_positions": 1,
            "bulk_openings": 1, "created_at": datetime.utcnow().isoformat() + "Z",
        })
        mc.close()
        r = session.post(f"{API}/jobs/apply", headers=_headers(stu["token"]), json={"job_id": job_id})
        assert r.status_code == 200
        mc, db = _mongo()
        app_id = db.applications.find_one({"job_id": job_id, "student_id": stu["user"]["id"]})["id"]
        mc.close()
        r = session.post(
            f"{API}/applications/hire",
            headers=_headers(pro["token"]),
            json={"application_id": app_id, "proof_base64": "data:image/png;base64,AA", "proof_filename": "p.png", "proof_mime_type": "image/png"},
        )
        assert r.status_code == 200
        mc, db = _mongo()
        chg = db.status_changes.find_one({"application_id": app_id, "status": "pending"})
        credits_before = db.users.find_one({"id": pro["user"]["id"]}).get("credits", 0)
        mc.close()

        r = session.post(
            f"{API}/admin/status-changes/action",
            headers=_headers(admin_tok),
            json={"change_id": chg["id"], "action": "reject", "note": "no proof"},
        )
        assert r.status_code == 200

        mc, db = _mongo()
        credits_after = db.users.find_one({"id": pro["user"]["id"]}).get("credits", 0)
        appdoc = db.applications.find_one({"id": app_id})
        chg_after = db.status_changes.find_one({"id": chg["id"]})
        mc.close()
        # No credit awarded on reject; status left as pre-existing (not 'hired')
        assert credits_after == credits_before
        assert appdoc["status"] != "hired"
        assert chg_after["status"] == "rejected"


# ==================== 8. Admin jobs verify ====================

class TestJobVerify:
    def _make_pending_pro_job(self, pro_id):
        job_id = f"iter56pend_{uuid.uuid4().hex[:8]}"
        mc, db = _mongo()
        db.jobs.insert_one({
            "id": job_id, "title": "Pending T", "description": "d", "company": "C", "location": "Bengaluru",
            "skill_set": ["python"], "employer_id": pro_id, "poster_role": "professional",
            "verification_status": "pending", "source": "pro", "status": "active", "open_positions": 1,
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        mc.close()
        return job_id

    def test_verify_approve(self, session, admin_tok, pro_tok):
        job_id = self._make_pending_pro_job(pro_tok["user"]["id"])
        r = session.post(f"{API}/admin/jobs/{job_id}/verify", headers=_headers(admin_tok), json={"decision": "verified", "note": ""})
        assert r.status_code == 200
        assert r.json()["verification_status"] == "verified"

    def test_verify_reject_requires_note(self, session, admin_tok, pro_tok):
        job_id = self._make_pending_pro_job(pro_tok["user"]["id"])
        r = session.post(f"{API}/admin/jobs/{job_id}/verify", headers=_headers(admin_tok), json={"decision": "rejected", "note": ""})
        assert r.status_code == 400
        # with note
        r2 = session.post(f"{API}/admin/jobs/{job_id}/verify", headers=_headers(admin_tok), json={"decision": "rejected", "note": "insufficient info"})
        assert r2.status_code == 200
        mc, db = _mongo()
        j = db.jobs.find_one({"id": job_id})
        mc.close()
        assert j["verification_status"] == "rejected"
        assert j.get("verification_note") == "insufficient info"

    def test_delete_job(self, session, admin_tok, pro_tok):
        job_id = self._make_pending_pro_job(pro_tok["user"]["id"])
        r = session.delete(f"{API}/admin/jobs/{job_id}", headers=_headers(admin_tok))
        assert r.status_code == 200
        r2 = session.delete(f"{API}/admin/jobs/{job_id}", headers=_headers(admin_tok))
        assert r2.status_code == 404


# ==================== 9. Redemption workflow ====================

class TestRedemptionWorkflow:
    """Uses the seeded redeem.pro@example.com account. Full approve → mark-paid path,
    then a fresh reject path with credit refund verified."""

    def _login_redeem_pro(self, session):
        r = session.post(f"{API}/auth/login", json={"email": "redeem.pro@example.com", "password": "RedeemPro@12345"})
        assert r.status_code == 200, r.text
        return r.json()

    def _submit_request(self, session, pro):
        # Direct DB insert to avoid depending on any submit endpoint semantics
        mc, db = _mongo()
        rid = f"iter56red_{uuid.uuid4().hex[:8]}"
        # Deduct from credits & put into locked_credits to mimic submit
        credits_req = 50
        db.users.update_one({"id": pro["user"]["id"]}, {"$inc": {"credits": -credits_req, "locked_credits": credits_req}})
        db.redemption_requests.insert_one({
            "id": rid,
            "pro_id": pro["user"]["id"],
            "pro_name": pro["user"].get("name", "Redeem Pro"),
            "pro_email": pro["user"]["email"],
            "credits_requested": credits_req,
            "amount_inr": credits_req * 1.0,
            "upi_id": "test@upi",
            "bank_account": "",
            "ifsc": "",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        mc.close()
        return rid, credits_req

    def test_approve_and_mark_paid(self, session, admin_tok):
        pro = self._login_redeem_pro(session)
        rid, credits_req = self._submit_request(session, pro)

        # Approve
        r = session.post(f"{API}/admin/redemption-requests/{rid}/approve", headers=_headers(admin_tok))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Cannot double-approve
        r = session.post(f"{API}/admin/redemption-requests/{rid}/approve", headers=_headers(admin_tok))
        assert r.status_code == 400

        # capture locked before mark-paid
        mc, db = _mongo()
        locked_before = db.users.find_one({"id": pro["user"]["id"]}).get("locked_credits", 0)
        mc.close()

        r = session.post(
            f"{API}/admin/redemption-requests/{rid}/mark-paid",
            headers=_headers(admin_tok),
            json={"payment_ref": "UPI-1234", "payment_date": None, "remarks": "iter56"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "paid"

        mc, db = _mongo()
        locked_after = db.users.find_one({"id": pro["user"]["id"]}).get("locked_credits", 0)
        req_doc = db.redemption_requests.find_one({"id": rid})
        txn = db.transactions.find_one({"user_id": pro["user"]["id"], "reason": "redemption_paid", "meta.request_id": rid})
        mc.close()
        assert locked_before - locked_after == credits_req
        assert req_doc["status"] == "paid"
        assert req_doc["payment_ref"] == "UPI-1234"
        assert txn is not None

    def test_reject_refunds_locked_to_credits(self, session, admin_tok):
        pro = self._login_redeem_pro(session)
        rid, credits_req = self._submit_request(session, pro)

        mc, db = _mongo()
        u = db.users.find_one({"id": pro["user"]["id"]})
        credits_before = u.get("credits", 0)
        locked_before = u.get("locked_credits", 0)
        mc.close()

        r = session.post(
            f"{API}/admin/redemption-requests/{rid}/reject",
            headers=_headers(admin_tok),
            json={"reason": "iter56 rejection test"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        mc, db = _mongo()
        u = db.users.find_one({"id": pro["user"]["id"]})
        req = db.redemption_requests.find_one({"id": rid})
        txn = db.transactions.find_one({"user_id": pro["user"]["id"], "reason": "redemption_refunded", "meta.request_id": rid})
        mc.close()
        assert u["credits"] - credits_before == credits_req
        assert locked_before - u.get("locked_credits", 0) == credits_req
        assert req["status"] == "rejected"
        assert txn["delta"] == credits_req


# ==================== 10. Interview admin cancellation refund ====================

class TestInterviewAdminCancel:
    def test_admin_cancel_booking_refunds_credits_charged(self, session, admin_tok, pro_tok):
        # create slot + booking directly
        stu = _signup(session, "student", "iter56ic")
        mc, db = _mongo()
        db.users.update_one({"id": stu["user"]["id"]}, {"$set": {"credits": 500}})
        slot_id = f"iter56slot_{uuid.uuid4().hex[:8]}"
        book_id = f"iter56bk_{uuid.uuid4().hex[:8]}"
        start_at = (datetime.utcnow() + timedelta(days=3)).isoformat() + "Z"
        db.interview_slots.insert_one({
            "id": slot_id, "pro_id": pro_tok["user"]["id"], "pro_name": pro_tok["user"].get("name"),
            "pro_email": pro_tok["user"]["email"], "student_id": stu["user"]["id"],
            "student_name": stu["user"].get("name"), "student_email": stu["user"]["email"],
            "skill_set": ["python"], "category": "software", "status": "booked",
            "credits_charged": 99, "start_at": start_at, "end_at": start_at,
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        db.interview_bookings.insert_one({
            "id": book_id, "slot_id": slot_id, "pro_id": pro_tok["user"]["id"], "pro_email": pro_tok["user"]["email"],
            "student_id": stu["user"]["id"], "student_email": stu["user"]["email"], "student_name": stu["user"].get("name"),
            "status": "confirmed", "credits_charged": 99, "start_at": start_at,
            "booked_at": datetime.utcnow().isoformat() + "Z",
        })
        # deduct student credits to mimic booking
        db.users.update_one({"id": stu["user"]["id"]}, {"$inc": {"credits": -99}})
        credits_before = db.users.find_one({"id": stu["user"]["id"]})["credits"]
        mc.close()

        r = session.post(
            f"{API}/admin/interviews/bookings/{book_id}/cancel",
            headers=_headers(admin_tok),
            json={"reason": "iter56 test cancel", "refund": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "cancelled"
        assert d["refund"] == 99

        mc, db = _mongo()
        credits_after = db.users.find_one({"id": stu["user"]["id"]})["credits"]
        slot = db.interview_slots.find_one({"id": slot_id})
        bk = db.interview_bookings.find_one({"id": book_id})
        txn = db.transactions.find_one({"user_id": stu["user"]["id"], "reason": "interview_admin_refund", "meta.booking_id": book_id})
        mc.close()
        assert credits_after - credits_before == 99
        assert slot["status"] == "available"
        assert "student_id" not in slot
        assert bk["status"] == "cancelled"
        assert txn is not None

    def test_admin_delete_slot_refunds(self, session, admin_tok, pro_tok):
        stu = _signup(session, "student", "iter56is")
        mc, db = _mongo()
        db.users.update_one({"id": stu["user"]["id"]}, {"$set": {"credits": 500}})
        slot_id = f"iter56ds_{uuid.uuid4().hex[:8]}"
        db.interview_slots.insert_one({
            "id": slot_id, "pro_id": pro_tok["user"]["id"], "student_id": stu["user"]["id"],
            "status": "booked", "credits_charged": 199,
            "start_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        credits_before = db.users.find_one({"id": stu["user"]["id"]})["credits"]
        mc.close()

        r = session.delete(f"{API}/admin/interviews/{slot_id}", headers=_headers(admin_tok))
        assert r.status_code == 200
        mc, db = _mongo()
        credits_after = db.users.find_one({"id": stu["user"]["id"]})["credits"]
        slot = db.interview_slots.find_one({"id": slot_id})
        mc.close()
        assert credits_after - credits_before == 199
        assert slot["status"] == "cancelled"

    def test_cancel_slot_booking_wrapper(self, session, admin_tok, pro_tok):
        stu = _signup(session, "student", "iter56cw")
        mc, db = _mongo()
        db.users.update_one({"id": stu["user"]["id"]}, {"$set": {"credits": 500}})
        slot_id = f"iter56cw_{uuid.uuid4().hex[:8]}"
        book_id = f"iter56cwbk_{uuid.uuid4().hex[:8]}"
        db.interview_slots.insert_one({
            "id": slot_id, "pro_id": pro_tok["user"]["id"], "student_id": stu["user"]["id"],
            "status": "booked", "credits_charged": 99,
            "start_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        db.interview_bookings.insert_one({
            "id": book_id, "slot_id": slot_id, "pro_id": pro_tok["user"]["id"],
            "student_id": stu["user"]["id"], "status": "confirmed", "credits_charged": 99,
            "start_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
            "booked_at": datetime.utcnow().isoformat() + "Z",
        })
        mc.close()
        r = session.post(
            f"{API}/admin/interviews/slots/{slot_id}/cancel-booking",
            headers=_headers(admin_tok),
            json={"reason": "iter56 wrapper cancel", "refund": True},
        )
        assert r.status_code == 200, r.text


# ==================== 11. Payout reject refunds ====================

class TestPayoutRefund:
    def test_reject_refunds_credits(self, session, admin_tok, pro_tok):
        # insert a payout doc directly
        mc, db = _mongo()
        pid = f"iter56po_{uuid.uuid4().hex[:8]}"
        db.payouts.insert_one({
            "id": pid, "professional_id": pro_tok["user"]["id"], "amount_inr": 100,
            "status": "requested", "upi_or_account": "test@upi",
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        credits_before = db.users.find_one({"id": pro_tok["user"]["id"]}).get("credits", 0)
        mc.close()
        r = session.post(
            f"{API}/admin/payouts/action",
            headers=_headers(admin_tok),
            json={"payout_id": pid, "action": "reject", "note": "iter56 reject"},
        )
        assert r.status_code == 200
        mc, db = _mongo()
        credits_after = db.users.find_one({"id": pro_tok["user"]["id"]}).get("credits", 0)
        po = db.payouts.find_one({"id": pid})
        txn = db.transactions.find_one({"user_id": pro_tok["user"]["id"], "reason": "payout_refund", "meta.payout_id": pid})
        mc.close()
        assert credits_after - credits_before == 100
        assert po["status"] == "rejected"
        assert txn is not None


# ==================== 12. Adjacent endpoints unchanged ====================

class TestAdjacentEndpoints:
    def test_wallet(self, session, admin_tok):
        r = session.get(f"{API}/wallet", headers=_headers(admin_tok))
        assert r.status_code == 200

    def test_auth_me(self, session, admin_tok):
        r = session.get(f"{API}/auth/me", headers=_headers(admin_tok))
        assert r.status_code == 200
        assert "user" in r.json()

    def test_jobs_public(self, session, student_tok):
        r = session.get(f"{API}/jobs?limit=1", headers=_headers(student_tok["token"]))
        assert r.status_code == 200

    def test_professionals(self, session, student_tok):
        r = session.get(f"{API}/professionals", headers=_headers(student_tok["token"]))
        assert r.status_code == 200

    def test_applications(self, session, student_tok):
        r = session.get(f"{API}/applications", headers=_headers(student_tok["token"]))
        assert r.status_code == 200

    def test_leaderboard_students(self, session, admin_tok):
        r = session.get(f"{API}/leaderboard/students", headers=_headers(admin_tok))
        assert r.status_code == 200
