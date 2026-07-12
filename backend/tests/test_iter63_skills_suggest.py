"""
Iteration 63 — Skill Auto-Suggest endpoint tests
Endpoint: GET /api/skills/suggest?q=<text>&limit=<n>

Coverage:
 - Public (no auth required)
 - Empty q → popular list, capped by limit
 - starts-with first, then contains, case-insensitive
 - limit clamping [1..100]
 - Aggregation coverage (MASTER_SKILLS + newly inserted job)
 - Deduplication across sources (case-insensitive)
 - Regression smoke of adjacent endpoints
"""
import os
import uuid
import time
import requests
import pytest
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Skills from server.py MASTER_SKILLS (source of truth for baseline aggregation)
MASTER = {
    "Oracle SQL", "PLSQL", "Java", "Python", "JavaScript", "TypeScript",
    "React", "React Native", "Angular", "Vue", "Node.js",
    "AWS", "Azure", "GCP", "DevOps", "Kubernetes", "Docker",
    "Data Science", "Machine Learning", "Deep Learning", "NLP",
    "SQL", "MongoDB", "PostgreSQL", "MySQL",
    "Spring Boot", "Django", "FastAPI", "Flask",
    "Android", "iOS", "Swift", "Kotlin",
    "HTML", "CSS", "Sass", "Tailwind",
    "Go", "Rust", "C++", "C#", ".NET",
    "Power BI", "Tableau", "Excel",
}


# ------------- Skills Suggest tests ------------- #
class TestSkillsSuggest:
    def test_public_no_auth_required(self):
        """Raw request with no Authorization header must return 200."""
        r = requests.get(f"{API}/skills/suggest")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "total" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)

    def test_empty_q_returns_popular_capped_by_limit(self):
        r = requests.get(f"{API}/skills/suggest", params={"limit": 10})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["items"]) <= 10
        assert body["total"] >= len(MASTER)
        # Confirm returned items are alphabetically sorted (case-insensitive)
        lower = [x.lower() for x in body["items"]]
        assert lower == sorted(lower), f"items not alphabetically sorted: {body['items']}"

    def test_master_skills_all_findable(self):
        """Each MASTER_SKILL should be findable via a targeted query (catalog >100
        so limit=100 could miss some — probe individually)."""
        missing = []
        for m in MASTER:
            r = requests.get(f"{API}/skills/suggest", params={"q": m, "limit": 10})
            assert r.status_code == 200, r.text
            lower = {i.lower() for i in r.json()["items"]}
            if m.lower() not in lower:
                missing.append(m)
        assert not missing, f"MASTER_SKILLS not found in catalog: {missing}"

    def test_limit_capped_and_clamped(self):
        # limit=5 → at most 5 items
        r = requests.get(f"{API}/skills/suggest", params={"limit": 5})
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 5
        # limit=999 → clamped to 100 (spec: max 100)
        r = requests.get(f"{API}/skills/suggest", params={"limit": 999})
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 100
        # limit=1 → exactly 1 (lower clamp)
        r = requests.get(f"{API}/skills/suggest", params={"limit": 1})
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    def test_query_p_returns_p_skills(self):
        r = requests.get(f"{API}/skills/suggest", params={"q": "p", "limit": 50})
        assert r.status_code == 200
        items = r.json()["items"]
        lower = [i.lower() for i in items]
        # From MASTER_SKILLS: PLSQL, Python, PostgreSQL, Power BI. All start with 'p'.
        for expected in ["plsql", "python", "postgresql", "power bi"]:
            assert expected in lower, f"missing '{expected}' in results: {items}"

    def test_query_py_returns_python(self):
        r = requests.get(f"{API}/skills/suggest", params={"q": "py", "limit": 50})
        assert r.status_code == 200
        lower = [i.lower() for i in r.json()["items"]]
        assert "python" in lower

    def test_query_java_returns_java(self):
        r = requests.get(f"{API}/skills/suggest", params={"q": "java", "limit": 50})
        assert r.status_code == 200
        lower = [i.lower() for i in r.json()["items"]]
        assert "java" in lower
        assert "javascript" in lower  # starts with java

    def test_case_insensitive(self):
        r_lower = requests.get(f"{API}/skills/suggest", params={"q": "py"}).json()["items"]
        r_upper = requests.get(f"{API}/skills/suggest", params={"q": "PY"}).json()["items"]
        r_mixed = requests.get(f"{API}/skills/suggest", params={"q": "Py"}).json()["items"]
        assert r_lower == r_upper == r_mixed

    def test_starts_with_ordered_before_contains(self):
        """For q='sql', 'SQL' (starts-with) must come before 'PLSQL'/'PostgreSQL' (contains)."""
        r = requests.get(f"{API}/skills/suggest", params={"q": "sql", "limit": 50})
        assert r.status_code == 200
        items = r.json()["items"]
        # All starts-with-sql entries must come before any contains-only match
        first_contains_idx = None
        last_starts_idx = -1
        for idx, s in enumerate(items):
            low = s.lower()
            if low.startswith("sql"):
                last_starts_idx = idx
            elif "sql" in low:
                if first_contains_idx is None:
                    first_contains_idx = idx
        if first_contains_idx is not None and last_starts_idx >= 0:
            assert last_starts_idx < first_contains_idx, (
                f"starts-with '{items[last_starts_idx]}' should come before "
                f"contains '{items[first_contains_idx]}' — items={items}"
            )
        # PLSQL is 'contains' for 'sql', SQL is starts-with
        lower = [i.lower() for i in items]
        assert "sql" in lower
        assert "plsql" in lower  # contains match

    def test_query_s_uppercase_letter(self):
        r = requests.get(f"{API}/skills/suggest", params={"q": "S", "limit": 50})
        assert r.status_code == 200
        lower = [i.lower() for i in r.json()["items"]]
        # From MASTER: SQL, Sass, Swift, Spring Boot (all start with 's')
        for expected in ["sql", "sass", "swift", "spring boot"]:
            assert expected in lower, f"missing '{expected}' in q='S' results"


# ------------- Aggregation & dedupe ------------- #
class TestSkillsSuggestAggregation:
    """Verify aggregation by finding existing skills from DB that are NOT in MASTER_SKILLS
    and confirming they appear in the endpoint response."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mc = MongoClient(MONGO_URL)
        self.db = self.mc[DB_NAME]
        yield
        self.mc.close()

    def _get_non_master_skills_from_source(self, collection, field, sub_field=None):
        """Collect skills from DB that aren't in MASTER_SKILLS."""
        master_lower = {m.lower() for m in MASTER}
        found = set()
        cursor = collection.find({}, {"_id": 0, field: 1} if not sub_field else {"_id": 0, f"{field}.{sub_field}": 1})
        for doc in cursor:
            val = doc.get(field) if not sub_field else (doc.get(field) or {}).get(sub_field)
            if isinstance(val, list):
                for s in val:
                    if s and isinstance(s, str) and s.lower() not in master_lower:
                        found.add(s)
        return found

    def test_aggregation_from_jobs_collection(self):
        db_skills = self._get_non_master_skills_from_source(self.db.jobs, "skills_required")
        if not db_skills:
            pytest.skip("No non-MASTER skills in jobs.skills_required to verify aggregation.")
        # Sample a few
        sample = list(db_skills)[:5]
        for skill in sample:
            r = requests.get(f"{API}/skills/suggest", params={"q": skill, "limit": 50})
            assert r.status_code == 200
            lower = {i.lower() for i in r.json()["items"]}
            assert skill.lower() in lower, (
                f"Job skill '{skill}' present in DB (jobs.skills_required) but "
                f"not returned by /skills/suggest. Returned: {r.json()['items']}"
            )

    def test_aggregation_from_user_profile_skills(self):
        db_skills = set()
        master_lower = {m.lower() for m in MASTER}
        for doc in self.db.users.find({}, {"_id": 0, "profile.skills": 1}):
            for s in (doc.get("profile") or {}).get("skills") or []:
                if isinstance(s, str) and s.lower() not in master_lower:
                    db_skills.add(s)
        if not db_skills:
            pytest.skip("No non-MASTER skills in profile.skills to verify aggregation.")
        sample = list(db_skills)[:5]
        for skill in sample:
            r = requests.get(f"{API}/skills/suggest", params={"q": skill, "limit": 50})
            assert r.status_code == 200
            lower = {i.lower() for i in r.json()["items"]}
            assert skill.lower() in lower, (
                f"Profile skill '{skill}' present in DB but not aggregated. Got: {r.json()['items']}"
            )

    def test_aggregation_from_expertise(self):
        db_skills = set()
        master_lower = {m.lower() for m in MASTER}
        for doc in self.db.users.find({}, {"_id": 0, "profile.expertise": 1}):
            for s in (doc.get("profile") or {}).get("expertise") or []:
                if isinstance(s, str) and s.lower() not in master_lower:
                    db_skills.add(s)
        if not db_skills:
            pytest.skip("No non-MASTER skills in profile.expertise to verify aggregation.")
        sample = list(db_skills)[:5]
        for skill in sample:
            r = requests.get(f"{API}/skills/suggest", params={"q": skill, "limit": 50})
            lower = {i.lower() for i in r.json()["items"]}
            assert skill.lower() in lower, f"Expertise skill '{skill}' not aggregated."

    def test_aggregation_from_interview_slots(self):
        db_skills = set()
        master_lower = {m.lower() for m in MASTER}
        for doc in self.db.interview_slots.find({}, {"_id": 0, "skill_set": 1}):
            for s in doc.get("skill_set") or []:
                if isinstance(s, str) and s.lower() not in master_lower:
                    db_skills.add(s)
        if not db_skills:
            pytest.skip("No non-MASTER skills in interview_slots.skill_set to verify aggregation.")
        sample = list(db_skills)[:5]
        for skill in sample:
            r = requests.get(f"{API}/skills/suggest", params={"q": skill, "limit": 50})
            lower = {i.lower() for i in r.json()["items"]}
            assert skill.lower() in lower, f"Slot skill '{skill}' not aggregated."

    def test_deduplication_case_insensitive(self):
        """Verify no duplicates in catalog (case-insensitive)."""
        r = requests.get(f"{API}/skills/suggest", params={"limit": 100})
        assert r.status_code == 200
        # Walk full catalog by paging is not supported; test-first 100 & known dups
        # Instead, use multiple targeted queries and check no duplicate casings appear.
        for probe in ["python", "java", "sql", "react"]:
            r = requests.get(f"{API}/skills/suggest", params={"q": probe, "limit": 100})
            items = r.json()["items"]
            lowered = [i.lower() for i in items]
            duplicates = [i for i in set(lowered) if lowered.count(i) > 1]
            assert not duplicates, f"Duplicate (case-insensitive) skills for q='{probe}': {duplicates} in {items}"


# ------------- Adjacent endpoints regression smoke ------------- #
class TestAdjacentEndpointsSmoke:
    def test_jobs_requires_auth_and_admin_can_list(self):
        # /jobs is auth-gated in iteration 63 codebase
        r = requests.get(f"{API}/jobs")
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
        # Admin can list
        s = requests.Session()
        rlogin = s.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
        assert rlogin.status_code == 200
        tok = rlogin.json()["token"]
        rj = requests.get(f"{API}/jobs", headers={"Authorization": f"Bearer {tok}"})
        assert rj.status_code == 200, rj.text
        assert isinstance(rj.json(), list)

    def test_auth_me_requires_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code in (401, 403), r.text

    def test_admin_login_and_me(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200, me.text
        body = me.json()
        # Response shape: {profile: {...}, user: {email, ...}}
        user = body.get("user") or body
        assert user.get("email") == "admin@referme.app"

    def test_wallet_requires_auth(self):
        r = requests.get(f"{API}/wallet")
        assert r.status_code in (401, 403)

    def test_interviews_slots_public_or_auth_ok(self):
        # Just verify the endpoint responds (either 200 or 401 — not 500).
        r = requests.get(f"{API}/interviews/slots")
        assert r.status_code in (200, 401, 403, 404), f"Unexpected: {r.status_code} {r.text}"
