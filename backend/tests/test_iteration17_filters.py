"""
Iteration 17 — Student Jobs filter rework backend regression.
Covers: GET /api/jobs?skill=&industry= filters and basic regressions
(auth, profile photo, jobs list).
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

DEMO_EMP = {"email": "demo-employer@referme.app", "password": "Demo@12345"}


# ---------- helpers ----------
def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _signup_student():
    email = f"TEST_stu_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "TestPass@123"
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={"email": email, "password": pwd, "role": "student", "name": "TEST Student"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    assert otp, "mock_otp not returned (TEST_RETURN_OTP=1 expected)"
    r2 = requests.post(
        f"{BASE_URL}/api/auth/verify-otp",
        json={"email": email, "otp": otp, "purpose": "verify_email"},
        timeout=30,
    )
    assert r2.status_code == 200, r2.text
    return r2.json()["token"], email


@pytest.fixture(scope="module")
def student_token():
    tok, _ = _signup_student()
    return tok


@pytest.fixture(scope="module")
def employer_token():
    return _login(DEMO_EMP["email"], DEMO_EMP["password"])


# ---------- seeding ----------
@pytest.fixture(scope="module")
def seeded_jobs(employer_token):
    """Seed two unique jobs to make skill/industry filter assertions deterministic."""
    h = {"Authorization": f"Bearer {employer_token}", "Content-Type": "application/json"}
    tag = uuid.uuid4().hex[:6]
    jobs = []

    java_job = {
        "title": f"TEST_Java_{tag}",
        "company": "TEST Co",
        "location": "Bangalore",
        "category": "experienced",
        "experience_min": 2,
        "experience_max": 5,
        "salary_range_label": "5-10",
        "open_positions": 1,
        "industry_type": "Software Services/IT",
        "skills_required": ["Java", "Spring Boot"],
        "description": "Java backend dev",
    }
    r = requests.post(f"{BASE_URL}/api/jobs", json=java_job, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    jobs.append(r.json()["id"])

    health_job = {
        "title": f"TEST_Health_{tag}",
        "company": "TEST Hospital",
        "location": "Mumbai",
        "category": "experienced",
        "experience_min": 1,
        "experience_max": 3,
        "salary_range_label": "3-5",
        "open_positions": 1,
        "industry_type": "Healthcare/Pharmaceuticals",
        "skills_required": ["Manual QA"],
        "description": "QA in healthcare",
    }
    r = requests.post(f"{BASE_URL}/api/jobs", json=health_job, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    jobs.append(r.json()["id"])

    yield {"tag": tag, "ids": jobs}

    # Cleanup
    for jid in jobs:
        try:
            requests.delete(f"{BASE_URL}/api/jobs/{jid}", headers=h, timeout=30)
        except Exception:
            pass


# ---------- skill filter ----------
class TestSkillFilter:
    def test_skill_java_returns_only_java_jobs(self, student_token, seeded_jobs):
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(f"{BASE_URL}/api/jobs?skill=Java", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        jobs = r.json()
        assert isinstance(jobs, list)
        # The Java job from seeding must be present
        java_ids = [j["id"] for j in jobs if j["id"] in seeded_jobs["ids"]]
        # All returned jobs that have skills_required must contain Java (case-insensitive)
        for j in jobs:
            sk = [s.lower() for s in (j.get("skills_required") or [])]
            assert any("java" in s for s in sk), f"job {j['id']} skills={sk} returned for skill=Java"
        # Java job seeded should appear
        assert any(jid == seeded_jobs["ids"][0] for jid in java_ids), "seeded Java job missing"

    def test_skill_case_insensitive(self, student_token, seeded_jobs):
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(f"{BASE_URL}/api/jobs?skill=java", headers=h, timeout=30)
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()]
        assert seeded_jobs["ids"][0] in ids

    def test_skill_salesforce_returns_no_seeded_match(self, student_token, seeded_jobs):
        """The empty-state path: filter by a skill no seeded job has."""
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(f"{BASE_URL}/api/jobs?skill=Salesforce", headers=h, timeout=30)
        assert r.status_code == 200
        jobs = r.json()
        # Neither of the two seeded jobs should be returned (they don't have Salesforce)
        for jid in seeded_jobs["ids"]:
            assert jid not in [j["id"] for j in jobs]


# ---------- industry filter ----------
class TestIndustryFilter:
    def test_industry_healthcare(self, student_token, seeded_jobs):
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(f"{BASE_URL}/api/jobs?industry=Healthcare", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        jobs = r.json()
        for j in jobs:
            assert "healthcare" in (j.get("industry_type") or "").lower()
        assert seeded_jobs["ids"][1] in [j["id"] for j in jobs]

    def test_industry_software_services_it_url_encoded(self, student_token, seeded_jobs):
        """The frontend sends 'Software Services/IT' URL-encoded."""
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(
            f"{BASE_URL}/api/jobs",
            params={"industry": "Software Services/IT"},
            headers=h,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        jobs = r.json()
        # Seeded Java job has industry 'Software Services/IT' → should be present
        assert seeded_jobs["ids"][0] in [j["id"] for j in jobs], "seeded SW Services/IT job missing"
        for j in jobs:
            assert "software services" in (j.get("industry_type") or "").lower()

    def test_skill_and_industry_combined(self, student_token, seeded_jobs):
        h = {"Authorization": f"Bearer {student_token}"}
        r = requests.get(
            f"{BASE_URL}/api/jobs",
            params={"skill": "Java", "industry": "Software Services/IT"},
            headers=h,
            timeout=30,
        )
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()]
        assert seeded_jobs["ids"][0] in ids
        assert seeded_jobs["ids"][1] not in ids


# ---------- regressions ----------
class TestRegressions:
    def test_auth_me(self, student_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {student_token}"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("user", {}).get("role") == "student"

    def test_employer_login_and_jobs_list(self, employer_token):
        r = requests.get(f"{BASE_URL}/api/jobs", headers={"Authorization": f"Bearer {employer_token}"}, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_profile_photo_base64_field_accepted(self, student_token):
        # Tiny 1x1 PNG base64
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AwAI/AL+5G4r"
            "0wAAAABJRU5ErkJggg=="
        )
        h = {"Authorization": f"Bearer {student_token}", "Content-Type": "application/json"}
        r = requests.put(
            f"{BASE_URL}/api/profile",
            json={"profile_photo_base64": f"data:image/png;base64,{png}"},
            headers=h,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {student_token}"}, timeout=30)
        assert r2.status_code == 200
        prof = r2.json().get("profile", {})
        assert prof.get("profile_photo_base64", "").startswith("data:image/png;base64,")

    def test_applications_list(self, student_token):
        r = requests.get(f"{BASE_URL}/api/applications", headers={"Authorization": f"Bearer {student_token}"}, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_interviews_list(self, student_token):
        r = requests.get(f"{BASE_URL}/api/interviews/mine", headers={"Authorization": f"Bearer {student_token}"}, timeout=30)
        # 200 with list expected (may be empty)
        assert r.status_code in (200, 404)
