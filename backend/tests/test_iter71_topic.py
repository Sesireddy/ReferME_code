"""Iter 71 — Mock Interview Topic + Skill Set business rules.

Validates POST /api/interviews/slots topic/skill_set rules, listing filter by topic,
and my-bookings exposure of `topic` field.
"""
import os
import uuid
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pathlib import Path

# Load backend env so MONGO_URL/DB_NAME are correct
_env_path = Path("/app/backend/.env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://refer-connect-11.preview.emergentagent.com"
).rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "referme_db")

ADMIN_EMAIL = "admin@referme.app"
ADMIN_PASSWORD = "Admin@12345"


# ------------- helpers -------------
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _post(path, token=None, **kw):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE_URL}{path}", headers=h, timeout=30, **kw)


def _get(path, token=None, **kw):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE_URL}{path}", headers=h, timeout=30, **kw)


def _signup_and_verify(email, password, role, extra=None):
    body = {"email": email, "password": password, "role": role}
    if extra:
        body.update(extra)
    r = _post("/api/auth/signup", json=body)
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text}"
    data = r.json()
    otp = data.get("mock_otp") or data.get("otp")
    assert otp, f"no mock_otp in signup response: {data}"
    r2 = _post("/api/auth/verify-otp", json={"email": email, "otp": otp})
    assert r2.status_code == 200, f"verify-otp failed: {r2.text}"
    return r2.json()["token"]


def _login(email, password):
    r = _post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


async def _mark_pro_verified(email):
    pass


def mark_pro_verified(email):
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    res = db.users.update_one(
        {"email": email},
        {"$set": {
            "profile.phone": "+919999999999",
            "profile.phone_verified": True,
            "profile.phone_verified_at": datetime.now(timezone.utc).isoformat(),
            "is_email_verified": True,
            "gmail_verified": True,
            "gmail_email": email,
        }},
    )
    client.close()
    return res.matched_count


def get_user_id(email):
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    doc = db.users.find_one({"email": email}, {"id": 1})
    client.close()
    return doc["id"] if doc else None


# ------------- fixtures -------------
@pytest.fixture(scope="module")
def pro_token():
    uniq = uuid.uuid4().hex[:8]
    email = f"iter71_pro_{uniq}@acmecorp.io"
    token = _signup_and_verify(email, "TestPro@12345", "professional", {"name": "Iter71 Pro"})
    mark_pro_verified(email)
    # relog to refresh flags on token/user cache if needed
    token = _login(email, "TestPro@12345")
    return {"token": token, "email": email}


@pytest.fixture(scope="module")
def student_token():
    uniq = uuid.uuid4().hex[:8]
    email = f"iter71_stu_{uniq}@example.com"
    token = _signup_and_verify(email, "TestStu@12345", "student", {"name": "Iter71 Stu"})
    return {"token": token, "email": email}


def _future_slot_bounds(offset_hours=2, minutes=30):
    # Round to next 30-minute boundary
    now = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    minute = 0 if now.minute < 30 else 30
    start = now.replace(minute=minute, second=0, microsecond=0)
    end = start + timedelta(minutes=minutes)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


# reserve non-conflicting hour windows for each test
_HOUR_OFFSETS = iter(range(2, 40))


def _next_bounds(minutes=30):
    off = next(_HOUR_OFFSETS)
    start_dt = datetime.now(timezone.utc) + timedelta(hours=off)
    start_dt = start_dt.replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(minutes=minutes)
    return (
        start_dt.isoformat().replace("+00:00", "Z"),
        end_dt.isoformat().replace("+00:00", "Z"),
    )


# ------------- tests -------------
class TestSlotCreateTopicRules:
    def test_1_career_guidance_overrides_skill_set(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "Career Guidance",
            "skill_set": ["React", "Foo"],
            "experience_years": 0,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["topic"] == "Career Guidance"
        assert body["skill_set"] == ["Career Guidance"], body
        # verify persisted slot
        slot_id = body["id"]
        listed = _get("/api/interviews/slots", token=pro_token["token"]).json()
        match = [s for s in listed if s["id"] == slot_id]
        assert match, "created slot not returned in list"
        assert match[0]["skill_set"] == ["Career Guidance"]
        assert match[0]["topic"] == "Career Guidance"

    def test_2_hr_discussion_overrides_empty_skill_set(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "HR Discussion",
            "skill_set": [],
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["skill_set"] == ["HR Discussion"]
        assert b["topic"] == "HR Discussion"

    def test_3_technical_uses_provided_skills(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "Technical Discussion",
            "skill_set": ["Java", "Spring Boot"],
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["skill_set"] == ["Java", "Spring Boot"]
        assert b["topic"] == "Technical Discussion"

    def test_4_technical_empty_skills_400(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "Technical Discussion",
            "skill_set": [],
        })
        assert r.status_code == 400, r.text
        assert "technical skill" in r.text.lower(), r.text

    def test_5_missing_topic_400(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "skill_set": ["Java"],
        })
        assert r.status_code == 400, r.text
        assert "topic" in r.text.lower(), r.text

    def test_6_invalid_topic_400(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "Random",
            "skill_set": ["Java"],
        })
        # Pydantic Literal will produce 422; spec says 400. Accept both but flag if 422.
        assert r.status_code in (400, 422), r.text
        # Prefer 400 per spec
        assert r.status_code == 400, f"Expected 400 per spec, got {r.status_code}: {r.text}"

    def test_7_case_insensitive_dedupe(self, pro_token):
        start, end = _next_bounds()
        r = _post("/api/interviews/slots", token=pro_token["token"], json={
            "start_at": start, "end_at": end,
            "topic": "Technical Discussion",
            "skill_set": ["Java", "java", "JAVA", "Spring"],
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["skill_set"] == ["Java", "Spring"], b["skill_set"]


class TestListAndBookings:
    def test_8_filter_by_topic(self, pro_token, student_token):
        pro_id = get_user_id(pro_token["email"])

        r = _get(
            "/api/interviews/slots",
            token=student_token["token"],
            params={"pro_id": pro_id, "topic": "Career Guidance"},
        )
        assert r.status_code == 200, r.text
        slots = r.json()
        assert len(slots) >= 1, "expected at least one Career Guidance slot"
        assert all(s.get("topic") == "Career Guidance" for s in slots), [s.get("topic") for s in slots]

        r2 = _get(
            "/api/interviews/slots",
            token=student_token["token"],
            params={"pro_id": pro_id, "topic": "Technical Discussion"},
        )
        assert r2.status_code == 200, r2.text
        s2 = r2.json()
        assert len(s2) >= 1
        assert all(s.get("topic") == "Technical Discussion" for s in s2)

        r3 = _get(
            "/api/interviews/slots",
            token=student_token["token"],
            params={"pro_id": pro_id, "topic": "HR Discussion"},
        )
        assert r3.status_code == 200
        s3 = r3.json()
        assert all(s.get("topic") == "HR Discussion" for s in s3)

        # topic present on every slot in listing (no filter)
        r4 = _get("/api/interviews/slots", token=student_token["token"], params={"pro_id": pro_id})
        assert r4.status_code == 200
        for s in r4.json():
            assert "topic" in s, "missing topic on listing item"

    def test_9_my_bookings_includes_topic(self, pro_token, student_token):
        pro_id = get_user_id(pro_token["email"])

        # Find an available Technical Discussion slot for this pro
        listed = _get(
            "/api/interviews/slots",
            token=student_token["token"],
            params={"pro_id": pro_id, "topic": "Technical Discussion"},
        ).json()
        avail = [s for s in listed if s.get("status") == "available"]
        assert avail, "no available Technical Discussion slot to book"
        slot = avail[0]

        r = _post(
            "/api/interviews/book",
            token=student_token["token"],
            json={"slot_id": slot["id"]},
        )
        assert r.status_code == 200, r.text

        # my-bookings must include topic
        mb = _get("/api/interviews/my-bookings", token=student_token["token"])
        assert mb.status_code == 200
        bookings = mb.json()
        assert bookings, "expected at least one booking"
        matching = [b for b in bookings if b["id"] == slot["id"]]
        assert matching, "booked slot missing from my-bookings"
        assert matching[0].get("topic") == "Technical Discussion", matching[0]
        # And every booking has a topic
        for b in bookings:
            assert "topic" in b, "missing topic on my-bookings item"
