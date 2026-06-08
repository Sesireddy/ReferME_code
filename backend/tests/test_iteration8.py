"""Iteration 8 — backend coverage:
   * GET /api/professionals (student) — has_available_slots default True (only pros with future slots).
   * GET /api/professionals — skill / location / category / date filters (partial + case-insensitive).
   * GET /api/jobs?location=Bangalore — synonyms (Bengaluru, Bombay/Mumbai).
   * GET /api/jobs?skill=java — partial case-insensitive (Core Java, Java Full Stack).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from conftest import API, auth_headers, _signup_verify, _gmail_verify_in_db  # type: ignore


# ---------- helpers ----------

def _make_pro_with_profile(session, *, expertise=None, location=None, exp_years=2):
    pro = _signup_verify(session, "professional")
    _gmail_verify_in_db(pro["user"]["id"])
    body = {
        "name": pro["user"].get("name") or "Pro Tester",
        "company": "AcmeCorp",
        "designation": "Senior Engineer",
        "experience_years": exp_years,
        "expertise": expertise or ["React"],
        "current_location": location or "Bengaluru",
        "skills": expertise or ["React"],
        "phone": "9999999999",
    }
    r = session.put(f"{API}/profile", json=body, headers=auth_headers(pro["token"]))
    assert r.status_code == 200, r.text
    return pro


def _create_future_slot(session, pro_token, *, hours_from_now=24, skill_set=None, exp_years=2):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    end = start + timedelta(minutes=60)
    body = {
        "start_at": start.isoformat().replace("+00:00", "Z"),
        "end_at": end.isoformat().replace("+00:00", "Z"),
        "skill_set": skill_set or ["React"],
        "category": "experienced",
        "experience_years": exp_years,
    }
    r = session.post(f"{API}/interviews/slots", json=body, headers=auth_headers(pro_token))
    assert r.status_code == 200, r.text
    return r.json()


def _post_job(session, token, *, title, skills, location, role="employer"):
    body = {
        "title": title,
        "description": f"{title} role for testing iteration 8",
        "skills_required": skills,
        "location": location,
        "company": "AcmeCorp",
        "category": "experienced",
        "experience_required": 2,
    }
    r = session.post(f"{API}/jobs", json=body, headers=auth_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


# ---------- /api/professionals filtering ----------

class TestProfessionalsHasAvailableSlots:
    """Verify default has_available_slots=true excludes pros with no future slots."""

    def test_pro_without_slots_excluded_for_students(self, session):
        student = _signup_verify(session, "student")
        pro_no_slots = _make_pro_with_profile(session, expertise=["NoSlotsSkillTagXYZ"])

        r = session.get(f"{API}/professionals", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert pro_no_slots["user"]["id"] not in ids, "Pro with no slots must be hidden by default"

    def test_pro_with_future_slot_included(self, session):
        student = _signup_verify(session, "student")
        pro = _make_pro_with_profile(session, expertise=["IterEightTag"])
        _create_future_slot(session, pro["token"], skill_set=["IterEightTag"])

        r = session.get(f"{API}/professionals", headers=auth_headers(student["token"]))
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert pro["user"]["id"] in ids, "Pro with future slot must be visible"

    def test_explicit_has_available_slots_false_includes_all(self, session):
        student = _signup_verify(session, "student")
        pro_no_slots = _make_pro_with_profile(session, expertise=["NoSlotsTagABC"])

        r = session.get(
            f"{API}/professionals?has_available_slots=false",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert pro_no_slots["user"]["id"] in ids


class TestProfessionalsFilters:
    """Skill / location / category / date filters on /api/professionals."""

    def test_skill_partial_case_insensitive(self, session):
        student = _signup_verify(session, "student")
        # Pro1 — expertise has 'Core Java'
        pro1 = _make_pro_with_profile(session, expertise=["Core Java", "Spring"])
        _create_future_slot(session, pro1["token"], skill_set=["Core Java"])
        # Pro2 — expertise has 'Python only' (should not match 'java')
        pro2 = _make_pro_with_profile(session, expertise=["Python"])
        _create_future_slot(session, pro2["token"], skill_set=["Python"])

        r = session.get(
            f"{API}/professionals?skill=java",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert pro1["user"]["id"] in ids
        assert pro2["user"]["id"] not in ids

    def test_location_partial_case_insensitive(self, session):
        student = _signup_verify(session, "student")
        unique = uuid.uuid4().hex[:6]
        pro = _make_pro_with_profile(
            session,
            expertise=[f"TagLoc{unique}"],
            location=f"Bengaluru-{unique}",
        )
        _create_future_slot(session, pro["token"], skill_set=[f"TagLoc{unique}"])

        r = session.get(
            f"{API}/professionals?location=bengaluru",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert pro["user"]["id"] in ids

    def test_category_fresher_vs_experienced(self, session):
        student = _signup_verify(session, "student")
        fresher = _make_pro_with_profile(session, expertise=["FreshTag"], exp_years=0)
        _create_future_slot(session, fresher["token"], skill_set=["FreshTag"], exp_years=0)
        exp_pro = _make_pro_with_profile(session, expertise=["ExpTag"], exp_years=5)
        _create_future_slot(session, exp_pro["token"], skill_set=["ExpTag"], exp_years=5)

        r = session.get(
            f"{API}/professionals?category=fresher",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert fresher["user"]["id"] in ids
        assert exp_pro["user"]["id"] not in ids

    def test_date_filter_matches_only_that_day(self, session):
        student = _signup_verify(session, "student")
        pro = _make_pro_with_profile(session, expertise=["DateFilterTag"])
        # Slot 48h in future
        slot = _create_future_slot(session, pro["token"], hours_from_now=48, skill_set=["DateFilterTag"])
        target_date = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00")).strftime("%Y-%m-%d")
        # Non-matching date 30 days ahead
        far_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")

        r_ok = session.get(
            f"{API}/professionals?date={target_date}",
            headers=auth_headers(student["token"]),
        )
        assert r_ok.status_code == 200
        assert pro["user"]["id"] in [p["id"] for p in r_ok.json()]

        r_no = session.get(
            f"{API}/professionals?date={far_date}",
            headers=auth_headers(student["token"]),
        )
        assert r_no.status_code == 200
        assert pro["user"]["id"] not in [p["id"] for p in r_no.json()]


# ---------- /api/jobs synonym + partial skill ----------

class TestJobsSynonyms:
    """City synonym expansion + partial case-insensitive skill match."""

    def test_location_bangalore_matches_bengaluru_job(self, session, employer):
        unique = uuid.uuid4().hex[:6]
        # Job posted with location 'Bengaluru'
        job = _post_job(
            session,
            employer["token"],
            title=f"TestJob-Bengaluru-{unique}",
            skills=[f"TagJobLoc{unique}"],
            location="Bengaluru",
        )
        # Search with 'Bangalore' — must hit the synonym
        student = _signup_verify(session, "student")
        r = session.get(
            f"{API}/jobs?location=Bangalore",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()]
        assert job["id"] in ids, "Bangalore search must return Bengaluru-located job via synonym"

    def test_location_bombay_matches_mumbai_job(self, session, employer):
        unique = uuid.uuid4().hex[:6]
        job = _post_job(
            session,
            employer["token"],
            title=f"TestJob-Mumbai-{unique}",
            skills=[f"TagJobMum{unique}"],
            location="Mumbai",
        )
        student = _signup_verify(session, "student")
        r = session.get(
            f"{API}/jobs?location=Bombay",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()]
        assert job["id"] in ids

    def test_skill_java_partial_match(self, session, employer):
        unique = uuid.uuid4().hex[:6]
        job_a = _post_job(
            session,
            employer["token"],
            title=f"TestJob-CoreJava-{unique}",
            skills=["Core Java", "JUnit"],
            location="Pune",
        )
        job_b = _post_job(
            session,
            employer["token"],
            title=f"TestJob-JavaFS-{unique}",
            skills=["Java Full Stack"],
            location="Pune",
        )
        job_other = _post_job(
            session,
            employer["token"],
            title=f"TestJob-Python-{unique}",
            skills=["Python", "Django"],
            location="Pune",
        )
        student = _signup_verify(session, "student")
        r = session.get(
            f"{API}/jobs?skill=java",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()]
        assert job_a["id"] in ids
        assert job_b["id"] in ids
        assert job_other["id"] not in ids

    def test_skill_sql_partial_match(self, session, employer):
        unique = uuid.uuid4().hex[:6]
        job_plsql = _post_job(
            session,
            employer["token"],
            title=f"TestJob-PLSQL-{unique}",
            skills=["PL/SQL"],
            location="Hyderabad",
        )
        job_oracle = _post_job(
            session,
            employer["token"],
            title=f"TestJob-OracleSQL-{unique}",
            skills=["Oracle SQL"],
            location="Hyderabad",
        )
        student = _signup_verify(session, "student")
        r = session.get(
            f"{API}/jobs?skill=sql",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()]
        assert job_plsql["id"] in ids
        assert job_oracle["id"] in ids


# ---------- expand_city sanity ----------

class TestExpandCityHelper:
    """Hit /api/jobs with each city synonym to verify expand_city covers all spec entries."""

    @pytest.mark.parametrize(
        "search_term,job_loc",
        [
            ("Chennai", "Madras"),
            ("Madras", "Chennai"),
            ("Kolkata", "Calcutta"),
            ("Calcutta", "Kolkata"),
            ("Gurgaon", "Gurugram"),
            ("Gurugram", "Gurgaon"),
            ("Trivandrum", "Thiruvananthapuram"),
            ("Thiruvananthapuram", "Trivandrum"),
        ],
    )
    def test_city_synonym_returns_matching_job(self, session, employer, search_term, job_loc):
        unique = uuid.uuid4().hex[:6]
        job = _post_job(
            session,
            employer["token"],
            title=f"TestJob-{job_loc}-{unique}",
            skills=[f"Tag{unique}"],
            location=job_loc,
        )
        student = _signup_verify(session, "student")
        r = session.get(
            f"{API}/jobs?location={search_term}",
            headers=auth_headers(student["token"]),
        )
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()]
        assert job["id"] in ids, f"Search '{search_term}' should match job in '{job_loc}'"
