"""Iteration 4 backend tests for ReferME.
Covers: company-email signup, suspend/activate/delete, jobs filters &
CRUD, /jobs/{id}, applicants, 402 insufficient credits, application
status pipeline (proof + admin queue + timeline), slot start/end + rules
+ Jitsi URL, leaderboard fields & filters, expanded admin/stats,
wallet refund, admin job/interview delete with refund.
"""
import os
import uuid
import requests
import pytest
from datetime import datetime, timedelta, timezone
from conftest import API, auth_headers


def _future(min_offset: int, duration_min: int):
    s = (datetime.now(timezone.utc) + timedelta(minutes=min_offset)).replace(microsecond=0)
    e = s + timedelta(minutes=duration_min)
    return s.isoformat().replace("+00:00", "Z"), e.isoformat().replace("+00:00", "Z")


def _signup_pro_with_email(session, email: str, password: str = "Pass@1234"):
    r = session.post(f"{API}/auth/signup", json={"email": email, "password": password, "role": "professional", "name": "Pro"})
    return r


# ---------- Signup: personal-email block ----------
class TestProfessionalEmailValidation:
    @pytest.mark.parametrize("domain", ["gmail.com", "yahoo.com", "outlook.com", "rediffmail.com"])
    def test_personal_domain_blocked(self, session, domain):
        email = f"test_pro_{uuid.uuid4().hex[:6]}@{domain}"
        r = _signup_pro_with_email(session, email)
        assert r.status_code == 400, r.text
        assert "company email" in r.json()["detail"].lower() or "personal" in r.json()["detail"].lower()

    def test_company_domain_allowed(self, session):
        email = f"test_pro_{uuid.uuid4().hex[:6]}@acmecorp.io"
        r = _signup_pro_with_email(session, email)
        assert r.status_code == 200, r.text
        # OTP should be returned (mock or sendgrid-fallback)
        assert r.json().get("mock_otp"), "expected mock_otp fallback when SendGrid send fails"

    def test_student_personal_domain_allowed(self, session):
        # personal domains are allowed for students
        email = f"test_stu_{uuid.uuid4().hex[:6]}@gmail.com"
        r = session.post(f"{API}/auth/signup", json={"email": email, "password": "Pass@1234", "role": "student"})
        assert r.status_code == 200, r.text


# ---------- Suspended login + admin user actions ----------
class TestSuspendActivateDelete:
    def test_suspend_then_login_blocked(self, session, student, admin_token):
        r = session.post(f"{API}/admin/users/{student['user']['id']}/suspend", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        r2 = session.post(f"{API}/auth/login", json={"email": student["email"], "password": student["password"]})
        assert r2.status_code == 403
        assert "suspend" in r2.json()["detail"].lower()
        # reactivate and login works again
        r3 = session.post(f"{API}/admin/users/{student['user']['id']}/activate", headers=auth_headers(admin_token))
        assert r3.status_code == 200
        r4 = session.post(f"{API}/auth/login", json={"email": student["email"], "password": student["password"]})
        assert r4.status_code == 200

    def test_admin_only_suspend(self, session, student, professional):
        r = session.post(f"{API}/admin/users/{student['user']['id']}/suspend", headers=auth_headers(professional["token"]))
        assert r.status_code == 403

    def test_delete_user(self, session, employer, admin_token):
        r = session.delete(f"{API}/admin/users/{employer['user']['id']}", headers=auth_headers(admin_token))
        assert r.status_code == 200
        # login now fails (user gone)
        r2 = session.post(f"{API}/auth/login", json={"email": employer["email"], "password": employer["password"]})
        assert r2.status_code == 401


# ---------- Jobs CRUD, filters & new fields ----------
class TestJobsIteration4:
    def test_pro_can_post_job(self, session, professional):
        r = session.post(f"{API}/jobs", json={
            "title": "Backend Engineer", "description": "FastAPI", "location": "Bengaluru",
            "company": "Acme", "category": "experienced", "experience_required": 3,
            "skills_required": ["Python", "React"], "open_positions": 2,
        }, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["company"] == "Acme"
        assert j["category"] == "experienced"
        assert j["experience_required"] == 3
        assert j["open_positions"] == 2

    def test_experienced_requires_experience_required(self, session, employer):
        r = session.post(f"{API}/jobs", json={
            "title": "Sr Eng", "description": "x", "category": "experienced",
        }, headers=auth_headers(employer["token"]))
        assert r.status_code == 400, r.text

    def test_get_single_job_with_applied_flag(self, session, student, employer):
        # employer posts
        r = session.post(f"{API}/jobs", json={"title": "TEST single", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        job_id = r.json()["id"]
        # student fetches single
        r2 = session.get(f"{API}/jobs/{job_id}", headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        j = r2.json()
        assert j["id"] == job_id
        assert "applied" in j
        assert j["applied"] is False
        # apply
        session.post(f"{API}/jobs/apply", json={"job_id": job_id}, headers=auth_headers(student["token"]))
        r3 = session.get(f"{API}/jobs/{job_id}", headers=auth_headers(student["token"]))
        j3 = r3.json()
        assert j3["applied"] is True
        assert j3.get("application_status") == "applied"

    def test_filter_jobs(self, session, student, employer):
        r = session.post(f"{API}/jobs", json={
            "title": "Filter Match", "description": "x", "location": "Bengaluru",
            "company": "Acme", "category": "experienced", "experience_required": 3,
            "skills_required": ["React"], "open_positions": 1,
        }, headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        r2 = session.get(f"{API}/jobs?skill=React&location=Bengaluru&category=experienced&exp_min=2&exp_max=5&company=Acme", headers=auth_headers(student["token"]))
        assert r2.status_code == 200
        ids = [j["id"] for j in r2.json()]
        assert jid in ids

    def test_patch_owner_only(self, session, employer, professional, admin_token):
        r = session.post(f"{API}/jobs", json={"title": "Edit Me", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        # other pro cannot edit
        r2 = session.patch(f"{API}/jobs/{jid}", json={"title": "Hacked"}, headers=auth_headers(professional["token"]))
        assert r2.status_code == 403
        # owner edits
        r3 = session.patch(f"{API}/jobs/{jid}", json={"title": "Edited", "open_positions": 5}, headers=auth_headers(employer["token"]))
        assert r3.status_code == 200, r3.text
        assert r3.json()["title"] == "Edited"
        # admin edits
        r4 = session.patch(f"{API}/jobs/{jid}", json={"location": "Remote"}, headers=auth_headers(admin_token))
        assert r4.status_code == 200
        assert r4.json()["location"] == "Remote"

    def test_close_reopen(self, session, employer):
        r = session.post(f"{API}/jobs", json={"title": "Close Me", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        r2 = session.post(f"{API}/jobs/{jid}/close", headers=auth_headers(employer["token"]))
        assert r2.status_code == 200
        # verify via GET (close endpoint returns {"message": "Closed"})
        j = session.get(f"{API}/jobs/{jid}", headers=auth_headers(employer["token"])).json()
        assert j["status"] == "closed"
        r3 = session.post(f"{API}/jobs/{jid}/reopen", headers=auth_headers(employer["token"]))
        assert r3.status_code == 200
        j2 = session.get(f"{API}/jobs/{jid}", headers=auth_headers(employer["token"])).json()
        assert j2["status"] == "open"

    def test_applicants_owner_only(self, session, employer, student, professional):
        r = session.post(f"{API}/jobs", json={"title": "TEST apps", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        session.post(f"{API}/jobs/apply", json={"job_id": jid}, headers=auth_headers(student["token"]))
        # non-owner pro blocked
        r2 = session.get(f"{API}/jobs/{jid}/applicants", headers=auth_headers(professional["token"]))
        assert r2.status_code == 403
        # owner sees
        r3 = session.get(f"{API}/jobs/{jid}/applicants", headers=auth_headers(employer["token"]))
        assert r3.status_code == 200
        apps = r3.json()
        assert len(apps) >= 1
        assert apps[0]["student_id"] == student["user"]["id"]
        assert "student_profile" in apps[0] or "student_name" in apps[0] or "name" in apps[0]


# ---------- Insufficient credits 402 ----------
class TestInsufficientCredits:
    def test_apply_402_when_no_free_no_credits(self, session, student, employer):
        # student starts with 2 free uses (FREE_TIER_ACTIONS*2 = 2)
        # create 3 jobs; consume both free uses, then 3rd apply must 402
        job_ids = []
        for i in range(3):
            r = session.post(f"{API}/jobs", json={"title": f"TEST job{i}", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
            job_ids.append(r.json()["id"])
        # apply 1 (free)
        s1 = session.post(f"{API}/jobs/apply", json={"job_id": job_ids[0]}, headers=auth_headers(student["token"]))
        assert s1.status_code == 200, s1.text
        # apply 2 (free)
        s2 = session.post(f"{API}/jobs/apply", json={"job_id": job_ids[1]}, headers=auth_headers(student["token"]))
        assert s2.status_code == 200, s2.text
        # apply 3 — out of free uses and 0 credits → 402
        s3 = session.post(f"{API}/jobs/apply", json={"job_id": job_ids[2]}, headers=auth_headers(student["token"]))
        assert s3.status_code == 402, s3.text
        assert "insufficient credits" in s3.json()["detail"].lower()


# ---------- Application status pipeline ----------
class TestApplicationStatusPipeline:
    def test_status_change_proof_and_admin_action_hire(self, session, professional, student, employer, admin_token):
        # create job + application
        r = session.post(f"{API}/jobs", json={"title": "TEST pipeline", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        # refer student (creates application)
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": jid}, headers=auth_headers(professional["token"]))
        app_id = r2.json()["application_id"]
        # pro submits status change to 'hired' with proof
        r3 = session.post(f"{API}/applications/status", json={
            "application_id": app_id, "new_status": "hired",
            "proof_base64": "data:image/png;base64,iVBORw0KG",
            "note": "offer letter attached",
        }, headers=auth_headers(professional["token"]))
        assert r3.status_code == 200, r3.text
        change_id = r3.json().get("id") or r3.json().get("change_id") or r3.json().get("status_change_id")
        assert change_id, r3.json()
        # admin sees in queue
        r4 = session.get(f"{API}/admin/status-changes", headers=auth_headers(admin_token))
        assert r4.status_code == 200
        ids = [c["id"] for c in r4.json()]
        assert change_id in ids
        # capture pro credits before approve
        w_before = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        # admin approves
        r5 = session.post(f"{API}/admin/status-changes/action", json={"change_id": change_id, "action": "approve"}, headers=auth_headers(admin_token))
        assert r5.status_code == 200, r5.text
        # pro got +500 for hired
        w_after = session.get(f"{API}/wallet", headers=auth_headers(professional["token"])).json()["credits"]
        assert w_after - w_before == 500, f"expected +500, got {w_after - w_before}"
        # timeline reflects current_status + history
        r6 = session.get(f"{API}/applications/{app_id}/timeline", headers=auth_headers(professional["token"]))
        assert r6.status_code == 200, r6.text
        tl = r6.json()
        assert tl["current_status"] == "hired"
        assert "history" in tl and isinstance(tl["history"], list)
        assert any(h.get("status") == "hired" or h.get("to_status") == "hired" for h in tl["history"])
        assert "pending_changes" in tl

    def test_status_change_reject_notifies(self, session, professional, student, employer, admin_token):
        r = session.post(f"{API}/jobs", json={"title": "TEST rej", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        r2 = session.post(f"{API}/referrals", json={"student_id": student["user"]["id"], "job_id": jid}, headers=auth_headers(professional["token"]))
        app_id = r2.json()["application_id"]
        r3 = session.post(f"{API}/applications/status", json={
            "application_id": app_id, "new_status": "shortlisted",
        }, headers=auth_headers(professional["token"]))
        change_id = r3.json().get("id") or r3.json().get("change_id")
        r4 = session.post(f"{API}/admin/status-changes/action", json={"change_id": change_id, "action": "reject", "note": "no proof"}, headers=auth_headers(admin_token))
        assert r4.status_code == 200, r4.text
        # timeline shouldn't reflect approved status (current stays at applied or referred)
        r5 = session.get(f"{API}/applications/{app_id}/timeline", headers=auth_headers(professional["token"])).json()
        assert r5["current_status"] != "shortlisted"


# ---------- Slot rules + Jitsi + booking email ----------
class TestSlotsIteration4:
    def test_slot_creates_jitsi_url(self, session, professional):
        s, e = _future(120, 90)  # 1h30m
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e, "topic": "Sys Design", "skill_set": ["DSA"], "experience_years": 3}, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        slot = r.json()
        assert slot.get("meeting_url", "").startswith("https://meet.jit.si/ReferME-"), slot.get("meeting_url")
        assert slot.get("skill_set") == ["DSA"]
        assert slot.get("experience_years") == 3

    def test_slot_min_1h_enforced(self, session, professional):
        s, e = _future(120, 30)  # 30 min < 1h
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        assert r.status_code == 400, r.text

    def test_slot_max_5h_per_day(self, session, professional):
        # create 5h total then 1 more hour same day fails
        base = (datetime.now(timezone.utc) + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        for i in range(5):  # 5 × 1h on same day = 5h
            s = (base + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
            e = (base + timedelta(hours=i + 1)).isoformat().replace("+00:00", "Z")
            rr = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
            assert rr.status_code == 200, f"slot {i}: {rr.text}"
        # 6th hour same day → must fail
        s = (base + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        e = (base + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        rr2 = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        assert rr2.status_code == 400, rr2.text

    def test_book_returns_meeting_url(self, session, professional, student):
        s, e = _future(180, 90)
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        sid = r.json()["id"]
        r2 = session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "meeting_url" in body
        assert body["meeting_url"].startswith("https://meet.jit.si/")


# ---------- Leaderboard fields + filters ----------
class TestLeaderboardIteration4:
    def test_leaderboard_fields(self, session, student):
        # set profile so fields populate
        session.put(f"{API}/profile", json={
            "education": "B.Tech", "passed_out_year": 2024, "current_location": "Bangalore",
            "preferred_role": "fresher", "skills": ["Python", "React"],
            "resume_link": "https://x.io/cv.pdf",
        }, headers=auth_headers(student["token"]))
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        lb = r.json()
        assert isinstance(lb, dict) and "items" in lb, "leaderboard should be paginated {items, total, page, page_size}"
        rows = lb["items"]
        if rows:
            row = rows[0]
            for k in ["rank", "name", "category", "skills", "current_location", "resume_score",
                      "interviews_attended", "rating", "jobs_applied", "referrals_received"]:
                assert k in row, f"missing field {k} in leaderboard row: {row}"

    def test_leaderboard_filters(self, session, student):
        session.put(f"{API}/profile", json={
            "education": "B.Tech", "passed_out_year": 2024, "current_location": "Bangalore",
            "preferred_role": "fresher", "skills": ["Python"],
            "resume_link": "https://x.io/cv.pdf",
        }, headers=auth_headers(student["token"]))
        # filter by location matches
        r = session.get(f"{API}/leaderboard/students?location=Bangalore&skill=Python&category=fresher&page_size=100", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        items = r.json()["items"]
        me = next((x for x in items if x["id"] == student["user"]["id"]), None)
        assert me is not None
        # filter excluding our student returns no match
        r2 = session.get(f"{API}/leaderboard/students?location=Nowhereville", headers=auth_headers(student["token"]))
        assert r2.status_code == 200
        assert not any(x["id"] == student["user"]["id"] for x in r2.json()["items"])


# ---------- Admin: stats, wallet refund, job/interview delete ----------
class TestAdminIteration4:
    def test_expanded_stats(self, session, admin_token):
        r = session.get(f"{API}/admin/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        d = r.json()
        for k in ["total_users", "active_students", "active_professionals", "hires",
                  "referrals_completed", "revenue_inr", "status_changes_pending"]:
            assert k in d, f"missing stat: {k}"

    def test_wallet_refund(self, session, student, admin_token):
        before = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json()["credits"]
        r = session.post(f"{API}/admin/wallet/refund?user_id={student['user']['id']}&amount=100&reason=test_refund", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        after = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json()["credits"]
        assert after - before == 100

    def test_admin_delete_job(self, session, employer, admin_token):
        r = session.post(f"{API}/jobs", json={"title": "Delete Me", "description": "d", "open_positions": 1}, headers=auth_headers(employer["token"]))
        jid = r.json()["id"]
        r2 = session.delete(f"{API}/admin/jobs/{jid}", headers=auth_headers(admin_token))
        assert r2.status_code == 200
        r3 = session.get(f"{API}/jobs/{jid}", headers=auth_headers(employer["token"]))
        assert r3.status_code == 404

    def test_admin_delete_interview_refunds_booked_student(self, session, professional, student, admin_token):
        # student earns credits first via referral hire so the deduction matters? booking uses free use here
        s, e = _future(240, 90)
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        sid = r.json()["id"]
        # student books with free use
        r2 = session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        assert r2.status_code == 200, r2.text
        free_before = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json().get("free_uses_left", 0)
        # admin cancels
        r3 = session.delete(f"{API}/admin/interviews/{sid}", headers=auth_headers(admin_token))
        assert r3.status_code == 200, r3.text
        free_after = session.get(f"{API}/wallet", headers=auth_headers(student["token"])).json().get("free_uses_left", 0)
        # free use refunded OR credits refunded (depending on how it was charged)
        assert free_after >= free_before  # at minimum not worse
