"""Iteration 28 — Working Professional Profile View/Edit Mode tests.

Covers:
  - PUT /api/profile by pro with NO profile_photo_base64 succeeds (photo optional)
  - PUT /api/profile accepts gender + education and persists them
  - GET /api/auth/me returns the persisted gender/education
  - Regression: missing_fields composition for pro after partial save
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
BASE_URL = (BASE_URL or "").rstrip("/")


def _signup_pro():
    email = f"itr28pro_{uuid.uuid4().hex[:8]}@acmecorp.io"
    password = "TestPass@123"
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={"email": email, "password": password, "name": "Iter28 Pro", "role": "professional"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text}"
    body = r.json()
    otp = body.get("mock_otp")
    assert otp, "mock_otp missing in signup response"

    r2 = requests.post(
        f"{BASE_URL}/api/auth/verify-otp",
        json={"email": email, "otp": otp},
        timeout=30,
    )
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    tok = r2.json().get("token")
    assert tok
    return email, tok


@pytest.fixture(scope="module")
def pro_session():
    email, tok = _signup_pro()
    return {"email": email, "token": tok}


def auth_headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# Feature: PUT /profile succeeds without profile_photo_base64 (photo optional)
def test_put_profile_no_photo_succeeds(pro_session):
    payload = {
        "name": "Iter28 Pro",
        "phone": "+919876543210",
        "company": "AcmeCorp",
        "designation": "Senior Engineer",
        "experience_years": 5,
        "current_location": "Bangalore",
        "skills": ["Python", "React"],
        "expertise": ["Python", "React"],
        # no profile_photo_base64 on purpose
    }
    r = requests.put(
        f"{BASE_URL}/api/profile",
        json=payload,
        headers=auth_headers(pro_session["token"]),
        timeout=30,
    )
    assert r.status_code == 200, f"PUT /profile failed: {r.status_code} {r.text}"
    # Verify via GET
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(pro_session["token"]), timeout=30)
    assert me.status_code == 200
    body = me.json()
    p = body.get("profile") or {}
    assert p.get("company") == "AcmeCorp"
    assert p.get("designation") == "Senior Engineer"


# Feature: PUT /profile accepts gender + education and persists them
def test_put_profile_with_gender_education(pro_session):
    payload = {
        "name": "Iter28 Pro",
        "phone": "+919876543210",
        "company": "AcmeCorp",
        "designation": "Senior Engineer",
        "experience_years": 5,
        "current_location": "Bangalore",
        "skills": ["Python"],
        "expertise": ["Python"],
        "gender": "male",
        "education": "Bachelor's",
    }
    r = requests.put(
        f"{BASE_URL}/api/profile",
        json=payload,
        headers=auth_headers(pro_session["token"]),
        timeout=30,
    )
    assert r.status_code == 200, f"PUT /profile failed: {r.status_code} {r.text}"
    body = r.json()
    # Endpoint may return updated profile inline; fall back to GET
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(pro_session["token"]), timeout=30)
    assert me.status_code == 200
    p = (me.json() or {}).get("profile") or {}
    assert p.get("gender") == "male", f"gender not persisted: {p}"
    assert p.get("education") == "Bachelor's", f"education not persisted: {p}"


# Feature: gender validates allowed enum values
def test_put_profile_invalid_gender_rejected(pro_session):
    r = requests.put(
        f"{BASE_URL}/api/profile",
        json={"gender": "invalid_value"},
        headers=auth_headers(pro_session["token"]),
        timeout=30,
    )
    assert r.status_code in (400, 422), f"expected validation error, got {r.status_code} {r.text}"


# Regression: missing_fields composition for pro
def test_pro_missing_fields_excludes_photo(pro_session):
    # After test_put_profile_no_photo_succeeds, all mandatory fields except gmail-verified
    # alternate gmail should be set. Photo NOT set. Photo should NOT block "profile_complete" per spec.
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(pro_session["token"]), timeout=30)
    assert me.status_code == 200
    body = me.json()
    missing = body.get("missing_fields") or []
    # Spec: Profile Photo is OPTIONAL on backend ("no pro_missing_fields entry")
    assert "Profile Photo" not in missing, (
        f"Backend still flagging 'Profile Photo' as missing — spec says it should be optional. missing={missing}"
    )
