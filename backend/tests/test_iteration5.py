"""Iteration 5 backend tests for ReferME.
Focus: /api/interviews/my-bookings endpoint + Jitsi meeting URL exposure +
freshly-signed-up user safe defaults (resume_score) + paginated leaderboard
shape + PUT /api/profile new fields (phone, profile_photo_base64,
certifications, projects) + TEST_RETURN_OTP mock fallback for signup &
forgot-password.
"""
import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from conftest import API, auth_headers


def _future(min_offset: int, duration_min: int):
    s = (datetime.now(timezone.utc) + timedelta(minutes=min_offset)).replace(microsecond=0)
    e = s + timedelta(minutes=duration_min)
    return s.isoformat().replace("+00:00", "Z"), e.isoformat().replace("+00:00", "Z")


# ---------- TEST_RETURN_OTP env flag ----------
class TestMockOTPReturn:
    def test_signup_returns_mock_otp(self, session):
        email = f"test_mock_{uuid.uuid4().hex[:8]}@acmecorp.io"
        r = session.post(f"{API}/auth/signup", json={
            "email": email, "password": "Pass@1234",
            "role": "professional", "name": "Mock Test",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mock_otp"), f"expected mock_otp, got {body}"
        # OTP is 6 digits
        assert len(str(body["mock_otp"])) == 6

    def test_forgot_password_returns_mock_otp(self, session, student):
        r = session.post(f"{API}/auth/forgot-password", json={"email": student["email"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mock_otp"), f"expected mock_otp, got {body}"


# ---------- Fresh user safe defaults (no profile yet) ----------
class TestFreshUserSafeDefaults:
    def test_auth_me_safe_for_fresh_user(self, session, student):
        r = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        # Should have user + (optional) profile without crashing
        assert "user" in data or "id" in data, data

    def test_leaderboard_safe_for_fresh_user(self, session, student):
        # student has no profile yet — must not crash
        r = session.get(f"{API}/leaderboard/students", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict) and "items" in body
        # Required paginated keys
        for k in ["items", "total", "page", "page_size"]:
            assert k in body, f"missing {k} in {body}"

    def test_profile_minimal_payload_ok(self, session, student):
        # PUT with minimal payload should not crash, resume_score returned
        r = session.put(f"{API}/profile", json={"current_location": "Mumbai"}, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        prof = body.get("profile") or body
        assert "resume_score" in prof, f"resume_score missing: {prof}"
        assert isinstance(prof["resume_score"], (int, float))
        # Safe default 0..100 range
        assert 0 <= prof["resume_score"] <= 100


# ---------- Paginated leaderboard shape ----------
class TestLeaderboardPagination:
    def test_pagination_shape_and_required_fields(self, session, student):
        # Set a minimal profile
        session.put(f"{API}/profile", json={
            "education": "B.Tech", "passed_out_year": 2024,
            "current_location": "Bangalore", "preferred_role": "fresher",
            "skills": ["Python"], "resume_link": "https://x.io/cv.pdf",
        }, headers=auth_headers(student["token"]))
        r = session.get(f"{API}/leaderboard/students?page=1&page_size=10", headers=auth_headers(student["token"]))
        assert r.status_code == 200
        body = r.json()
        for k in ["items", "total", "page", "page_size"]:
            assert k in body, f"missing key {k}: {body}"
        assert body["page"] == 1
        assert body["page_size"] == 10
        items = body["items"]
        assert isinstance(items, list)
        # Verify each item has required fields
        required = ["rank", "name", "category", "skills", "current_location",
                    "resume_score", "interviews_attended", "rating",
                    "jobs_applied", "referrals_received", "composite_score", "is_me"]
        if items:
            row = items[0]
            for k in required:
                assert k in row, f"missing field '{k}' in row: {row}"
        # Find self row, is_me flag should be True for at least one row
        me = next((x for x in items if x.get("id") == student["user"]["id"]), None)
        if me is not None:
            assert me["is_me"] is True, me


# ---------- PUT /api/profile new fields ----------
class TestProfileNewFields:
    def test_profile_persists_phone_photo_certs_projects(self, session, student):
        png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
        payload = {
            "phone": "+919876543210",
            "profile_photo_base64": png_b64,
            "education": "B.Tech",
            "passed_out_year": 2024,
            "skills": ["Python", "React"],
            "current_location": "Bangalore",
            "preferred_role": "fresher",
            "resume_link": "https://x.io/cv.pdf",
            "certifications": [
                {"title": "AWS SAA", "issuer": "Amazon", "year": 2024, "link": "https://aws.cert/x"},
                {"title": "GCP ACE", "issuer": "Google", "year": 2023},
            ],
            "projects": [
                {"title": "Portfolio Site", "description": "Personal portfolio", "link": "https://me.io"},
                {"title": "Chat App", "description": "Realtime chat", "tech": ["Node", "Socket"]},
            ],
        }
        r = session.put(f"{API}/profile", json=payload, headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        prof = body.get("profile") or body
        assert prof.get("phone") == "+919876543210"
        assert prof.get("profile_photo_base64") == png_b64
        certs = prof.get("certifications") or []
        assert len(certs) == 2
        assert certs[0]["title"] == "AWS SAA"
        projects = prof.get("projects") or []
        assert len(projects) == 2
        assert projects[0]["title"] == "Portfolio Site"
        # resume_score auto-recomputed and returned
        assert "resume_score" in prof
        assert isinstance(prof["resume_score"], (int, float))

        # GET via /auth/me reflects persisted values
        me = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
        assert me.status_code == 200
        me_body = me.json()
        mp = me_body.get("profile") or {}
        assert mp.get("phone") == "+919876543210"
        assert (mp.get("certifications") or [])[0]["title"] == "AWS SAA"


# ---------- /api/interviews/my-bookings ----------
class TestMyBookings:
    def test_student_sees_booked_slots_with_counterparty(self, session, professional, student):
        s, e = _future(120, 90)
        r = session.post(f"{API}/interviews/slots", json={
            "start_at": s, "end_at": e, "topic": "DSA Round", "skill_set": ["DSA"],
        }, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        slot = r.json()
        assert slot["meeting_url"].startswith("https://meet.jit.si/ReferME-"), slot["meeting_url"]
        sid = slot["id"]

        # student books
        rb = session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        assert rb.status_code == 200, rb.text
        assert rb.json().get("meeting_url") == slot["meeting_url"]

        # student my-bookings
        rm = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(student["token"]))
        assert rm.status_code == 200, rm.text
        items = rm.json()
        assert isinstance(items, list)
        my = next((x for x in items if x["id"] == sid), None)
        assert my is not None, f"booked slot missing: {items}"
        assert my.get("meeting_url") == slot["meeting_url"]
        assert "counterparty_name" in my
        # counterparty is the pro (whatever pro_name is, str or None)
        assert "join_enabled" in my and isinstance(my["join_enabled"], bool)

    def test_pro_sees_booked_slot_with_student_as_counterparty(self, session, professional, student):
        s, e = _future(120, 90)
        r = session.post(f"{API}/interviews/slots", json={
            "start_at": s, "end_at": e,
        }, headers=auth_headers(professional["token"]))
        sid = r.json()["id"]
        # Book
        session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        # Pro view
        rp = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(professional["token"]))
        assert rp.status_code == 200
        items = rp.json()
        # only slots with student assigned should appear
        my = next((x for x in items if x["id"] == sid), None)
        assert my is not None, items
        # counterparty for pro = student
        assert "counterparty_name" in my
        assert "join_enabled" in my

    def test_employer_my_bookings_empty(self, session, employer):
        r = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(employer["token"]))
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_admin_my_bookings_empty(self, session, admin_token):
        r = session.get(f"{API}/interviews/my-bookings", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_join_enabled_window(self, session, professional, student):
        # Slot starting in 5 min (within 10-min pre-window) → join_enabled True
        s = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0)
        e = s + timedelta(minutes=60)
        sj = s.isoformat().replace("+00:00", "Z")
        ej = e.isoformat().replace("+00:00", "Z")
        r = session.post(f"{API}/interviews/slots", json={"start_at": sj, "end_at": ej}, headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        items = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(student["token"])).json()
        my = next((x for x in items if x["id"] == sid), None)
        assert my is not None
        assert my["join_enabled"] is True, my

    def test_join_enabled_false_for_far_future(self, session, professional, student):
        # Slot far in future (>10 min) → join_enabled False
        s, e = _future(120, 60)
        r = session.post(f"{API}/interviews/slots", json={"start_at": s, "end_at": e}, headers=auth_headers(professional["token"]))
        sid = r.json()["id"]
        session.post(f"{API}/interviews/book", json={"slot_id": sid}, headers=auth_headers(student["token"]))
        items = session.get(f"{API}/interviews/my-bookings", headers=auth_headers(student["token"])).json()
        my = next((x for x in items if x["id"] == sid), None)
        assert my is not None
        assert my["join_enabled"] is False, my
