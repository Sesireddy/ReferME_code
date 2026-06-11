"""Iteration 10 backend tests — Employer signup block + Student ranks endpoint.

Covers:
- POST /api/auth/signup with role='employer' → 400 with exact 'For employer assistance...' message.
- GET /api/leaderboard/student/me/ranks → 200 with keys overall_rank, category_rank,
  skill_rank, primary_skill, category_label, resume_score.
- Auth/role guard on the ranks endpoint (pro/employer → 403).
"""
from __future__ import annotations

import uuid

from conftest import API, _signup_verify, auth_headers  # type: ignore


EMPLOYER_BLOCK_MSG = "For employer assistance, please contact our team at Team@referme.today"


# ------------------- Employer signup is blocked -------------------
class TestEmployerSignupBlocked:
    def test_signup_role_employer_returns_400_with_contact_message(self, session):
        email = f"test_employer_block_{uuid.uuid4().hex[:8]}@referme.io"
        r = session.post(
            f"{API}/auth/signup",
            json={"email": email, "password": "Test@12345", "role": "employer", "name": "Blocked Emp"},
        )
        assert r.status_code == 400, r.text
        assert r.json().get("detail") == EMPLOYER_BLOCK_MSG, r.text

    def test_signup_role_employer_blocked_even_with_company_domain(self, session):
        # Should be blocked regardless of email domain.
        email = f"corp_emp_{uuid.uuid4().hex[:8]}@acmecorp.io"
        r = session.post(
            f"{API}/auth/signup",
            json={"email": email, "password": "Test@12345", "role": "employer", "name": "Corp Emp"},
        )
        assert r.status_code == 400
        assert r.json().get("detail") == EMPLOYER_BLOCK_MSG

    def test_signup_student_still_works(self, session):
        # Sanity: signup still works for non-employer roles after the block.
        s = _signup_verify(session, "student", prefix="iter10")
        assert s["user"]["role"] == "student"


# ------------------- /leaderboard/student/me/ranks -------------------
EXPECTED_KEYS = {
    "overall_rank",
    "category_rank",
    "skill_rank",
    "primary_skill",
    "category_label",
    "resume_score",
}


class TestStudentMeRanks:
    def test_ranks_returns_all_keys_for_fresh_student(self, session, student):
        r = session.get(
            f"{API}/leaderboard/student/me/ranks",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) == EXPECTED_KEYS, data
        # Fresh student → resume_score 0, overall_rank >= 1
        assert isinstance(data["overall_rank"], int) and data["overall_rank"] >= 1
        assert data["resume_score"] == 0
        # category_rank / skill_rank / primary_skill / category_label may be null for a fresh student
        # but if present must be int / str
        if data["category_rank"] is not None:
            assert isinstance(data["category_rank"], int)
        if data["skill_rank"] is not None:
            assert isinstance(data["skill_rank"], int)
        if data["primary_skill"] is not None:
            assert isinstance(data["primary_skill"], str)

    def test_ranks_after_profile_update_picks_up_primary_skill_and_category(self, session, student):
        # Update profile with a primary_skill + preferred_role + resume_score, then call ranks.
        payload = {
            "name": "Iter10 Student",
            "skills": ["React", "Python"],
            "preferred_role": "fresher",
            "passed_out_year": 2024,
            "resume_score": 72,
        }
        r0 = session.put(
            f"{API}/profile",
            headers=auth_headers(student["token"]),
            json=payload,
        )
        assert r0.status_code == 200, r0.text
        r = session.get(
            f"{API}/leaderboard/student/me/ranks",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["primary_skill"] == "React"
        assert data["category_label"] == "fresher"
        # resume_score may or may not be writable via /profile; assert it's an int
        assert isinstance(data["resume_score"], int)
        # skill_rank/category_rank become non-null now that primary_skill + preferred_role exist
        assert data["skill_rank"] is not None and data["skill_rank"] >= 1
        assert data["category_rank"] is not None and data["category_rank"] >= 1

    def test_ranks_forbidden_for_pro(self, session, professional):
        r = session.get(
            f"{API}/leaderboard/student/me/ranks",
            headers=auth_headers(professional["token"]),
        )
        assert r.status_code == 403, r.text

    def test_ranks_forbidden_for_employer(self, session, employer):
        r = session.get(
            f"{API}/leaderboard/student/me/ranks",
            headers=auth_headers(employer["token"]),
        )
        assert r.status_code == 403, r.text

    def test_ranks_requires_auth(self, session):
        r = session.get(f"{API}/leaderboard/student/me/ranks")
        # missing bearer → 401 (or 403 depending on middleware)
        assert r.status_code in (401, 403), r.text
