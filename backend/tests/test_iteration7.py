"""Iteration 7 backend tests — Pro Profile Completion, Alternate Gmail OTP, expanded PRO_PROFILE_FIELDS,
and /jobs?mine=true (no trailing-slash 307) regression.
"""
import os
import uuid
import requests
import pytest
from conftest import _signup_verify, auth_headers, API


# ------------------------- /auth/me for pro -------------------------

def test_auth_me_pro_includes_profile_completion(session, professional):
    r = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
    assert r.status_code == 200, r.text
    j = r.json()
    assert "profile_completion" in j and isinstance(j["profile_completion"], int)
    assert 0 <= j["profile_completion"] <= 100
    u = j["user"]
    # Spec: company email verified=true at signup
    assert u.get("email_verified") is True
    # New flags present
    assert "gmail_verified" in u
    assert "alternate_gmail" in u
    assert u["gmail_verified"] is False  # brand-new pro
    assert u["alternate_gmail"] in (None, "", False) or u["alternate_gmail"] is None


def test_auth_me_student_does_not_have_profile_completion(session, student):
    """profile_completion is pro-only (sanity)."""
    r = session.get(f"{API}/auth/me", headers=auth_headers(student["token"]))
    assert r.status_code == 200
    j = r.json()
    assert "profile_completion" not in j


# ------------------------- Gmail OTP — send -------------------------

def test_gmail_send_otp_rejects_non_gmail_domain(session, professional):
    r = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": "alt@yahoo.com"},
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 400
    assert "gmail" in r.text.lower()


def test_gmail_send_otp_rejects_same_as_login_email(session, professional):
    r = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": professional["email"]},
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 400


def test_gmail_send_otp_rejects_invalid_email(session, professional):
    r = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": "not-an-email"},
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 400


def test_gmail_send_otp_success_returns_mock_otp(session, professional):
    alt = f"refertest_{uuid.uuid4().hex[:8]}@gmail.com"
    r = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": alt},
        headers=auth_headers(professional["token"]),
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("mock_otp"), "mock_otp must be returned under TEST_RETURN_OTP=1"
    assert isinstance(j["mock_otp"], str) and len(j["mock_otp"]) == 6


def test_gmail_send_otp_blocks_for_non_pro(session, student):
    r = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": "alt@gmail.com"},
        headers=auth_headers(student["token"]),
    )
    assert r.status_code in (401, 403)


# ------------------------- Gmail OTP — verify -------------------------

def test_gmail_verify_wrong_otp_returns_400(session, professional):
    alt = f"refertest_{uuid.uuid4().hex[:8]}@gmail.com"
    s = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": alt},
        headers=auth_headers(professional["token"]),
    )
    assert s.status_code == 200
    v = session.post(
        f"{API}/pro/gmail/verify-otp",
        json={"email": alt, "otp": "000000"},
        headers=auth_headers(professional["token"]),
    )
    assert v.status_code == 400


def test_gmail_verify_no_pending_returns_400(session, professional):
    # Verify without sending should fail
    v = session.post(
        f"{API}/pro/gmail/verify-otp",
        json={"email": f"nopending_{uuid.uuid4().hex[:6]}@gmail.com", "otp": "123456"},
        headers=auth_headers(professional["token"]),
    )
    assert v.status_code == 400


def test_gmail_verify_success_sets_user_flags(session, professional):
    alt = f"refertest_{uuid.uuid4().hex[:8]}@gmail.com"
    s = session.post(
        f"{API}/pro/gmail/send-otp",
        json={"email": alt},
        headers=auth_headers(professional["token"]),
    )
    assert s.status_code == 200, s.text
    code = s.json()["mock_otp"]
    v = session.post(
        f"{API}/pro/gmail/verify-otp",
        json={"email": alt, "otp": code},
        headers=auth_headers(professional["token"]),
    )
    assert v.status_code == 200, v.text
    assert v.json().get("alternate_gmail") == alt

    me = session.get(f"{API}/auth/me", headers=auth_headers(professional["token"]))
    assert me.status_code == 200
    j = me.json()
    assert j["user"]["gmail_verified"] is True
    assert j["user"]["alternate_gmail"] == alt
    # profile.alternate_gmail mirrored
    assert (j.get("profile") or {}).get("alternate_gmail") == alt


# ------------------------- profile_completion math -------------------------

def test_profile_completion_increases_with_fields(session, professional):
    h = auth_headers(professional["token"])

    me0 = session.get(f"{API}/auth/me", headers=h).json()
    base = me0["profile_completion"]
    # Brand-new pro has only Company Email Verified factor -> 1/7 -> ~14
    assert 10 <= base <= 20, f"expected ~14, got {base}"

    # Add phone, designation, experience, skills, profile photo via PUT /profile
    r = session.put(
        f"{API}/profile",
        json={
            "phone": "+919876543210",
            "designation": "Senior Engineer",
            "experience_years": 5,
            "skills": ["Python", "FastAPI"],
            "profile_photo_base64": "data:image/png;base64,iVBORw0KGgo=",
            "current_location": "Bangalore",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text

    me1 = session.get(f"{API}/auth/me", headers=h).json()
    # 1 (email) + 5 added = 6 / 7 = ~86
    assert me1["profile_completion"] >= base + 50
    assert 80 <= me1["profile_completion"] <= 90, f"expected ~86, got {me1['profile_completion']}"

    # Add Gmail verification (last factor) -> 7/7 -> 100
    alt = f"complete_{uuid.uuid4().hex[:8]}@gmail.com"
    s = session.post(f"{API}/pro/gmail/send-otp", json={"email": alt}, headers=h)
    code = s.json()["mock_otp"]
    v = session.post(f"{API}/pro/gmail/verify-otp", json={"email": alt, "otp": code}, headers=h)
    assert v.status_code == 200

    me2 = session.get(f"{API}/auth/me", headers=h).json()
    assert me2["profile_completion"] == 100


# ------------------------- PRO_PROFILE_FIELDS persistence -------------------------

def test_pro_profile_fields_persist(session, professional):
    h = auth_headers(professional["token"])
    payload = {
        "phone": "+919999988888",
        "current_location": "Hyderabad",
        "skills": ["React", "System Design", "Java"],
        "profile_photo_base64": "data:image/png;base64,ABCDEFG",
        "designation": "Staff Engineer",
        "experience_years": 8,
        "company": "AcmeCorp",
    }
    r = session.put(f"{API}/profile", json=payload, headers=h)
    assert r.status_code == 200

    me = session.get(f"{API}/auth/me", headers=h).json()
    p = me["profile"]
    assert p.get("phone") == payload["phone"]
    assert p.get("current_location") == payload["current_location"]
    assert p.get("skills") == payload["skills"]
    assert p.get("profile_photo_base64") == payload["profile_photo_base64"]
    assert p.get("designation") == payload["designation"]
    assert p.get("experience_years") == payload["experience_years"]
    assert p.get("company") == payload["company"]


def test_pro_profile_accepts_alternate_gmail_field_but_does_not_verify(session, professional):
    """ProfileBody now accepts alternate_gmail — but writing it via PUT /profile
    should NOT set gmail_verified (that requires the OTP flow)."""
    h = auth_headers(professional["token"])
    alt = f"raw_{uuid.uuid4().hex[:6]}@gmail.com"
    r = session.put(f"{API}/profile", json={"alternate_gmail": alt}, headers=h)
    assert r.status_code == 200
    me = session.get(f"{API}/auth/me", headers=h).json()
    # Stored in profile
    assert (me.get("profile") or {}).get("alternate_gmail") == alt
    # Not auto-verified
    assert me["user"]["gmail_verified"] is False


# ------------------------- /jobs?mine=true regression (no 307) -------------------------

def test_jobs_mine_true_no_trailing_slash_no_redirect(session, professional):
    """Calling /api/jobs?mine=true (no trailing slash) should return 200 directly,
    not a 307 redirect. The frontend depends on this."""
    h = auth_headers(professional["token"])
    # Disable redirect-following so we observe the raw status.
    r = requests.get(f"{API}/jobs?mine=true", headers=h, allow_redirects=False)
    assert r.status_code == 200, f"expected 200 directly, got {r.status_code}; location={r.headers.get('location')}"
    body = r.json()
    assert isinstance(body, list)


def test_jobs_mine_true_returns_only_caller_jobs(session, professional):
    h = auth_headers(professional["token"])
    # Create a job as this pro
    job = {
        "title": "TEST iter7 mine=true",
        "description": "test",
        "location": "Bangalore",
        "skills": ["Python"],
        "experience_min": 1,
        "experience_max": 3,
        "salary_min": 100000,
        "salary_max": 200000,
    }
    cr = session.post(f"{API}/jobs", json=job, headers=h)
    assert cr.status_code == 200, cr.text
    job_id = cr.json()["id"]

    r = requests.get(f"{API}/jobs?mine=true", headers=h)
    assert r.status_code == 200
    items = r.json()
    assert any(j["id"] == job_id for j in items)
    assert all(j.get("employer_id") == professional["user"]["id"] for j in items), "mine=true should only return caller's jobs"
