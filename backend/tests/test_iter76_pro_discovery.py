"""Iter 76 — Mock Interviews screen must list ALL professionals with active future slots.

Regression for bug: on job seeker → Mock Interviews only 1 of several professionals'
slots was showing. Root cause: the `/api/professionals` endpoint fetched the first
500 pros then aggregated slots — so pros positioned past #500 in natural DB order
were silently dropped even if they had active availability.

Fix inverted the flow: aggregate the interview_slots collection first to find the
pros with future availability, then look up ONLY those users. This test creates 3
pros with future slots and 600+ noise pros to ensure the endpoint returns all 3
regardless of DB ordering.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pathlib import Path

# Load backend env
_env_path = Path("/app/backend/.env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "referme_db")


def _api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _mint_student_token(sid: str) -> str:
    """Bypass OTP by minting a JWT directly (mirrors create_jwt in server)."""
    import jwt
    from datetime import datetime, timedelta, timezone as _tz
    secret = os.environ.get("JWT_SECRET", "change-me-in-production")
    alg = os.environ.get("JWT_ALG", "HS256")
    exp_min = int(os.environ.get("JWT_EXPIRES_MIN", "1440"))
    payload = {
        "sub": sid,
        "role": "student",
        "exp": datetime.now(_tz.utc) + timedelta(minutes=exp_min),
        "iat": datetime.now(_tz.utc),
    }
    return jwt.encode(payload, secret, algorithm=alg)


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def scenario(db):
    """Seed 3 professionals with future slots + a student to query the list."""
    tag = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)

    pros = []
    # Assign a different topic to each pro to ensure per-topic isolation:
    #   i=0 → Technical Discussion, i=1 → HR Discussion, i=2 → Career Guidance
    topics_by_i = ["Technical Discussion", "HR Discussion", "Career Guidance"]
    for i in range(3):
        pid = f"iter76-pro-{tag}-{i}"
        db.users.update_one(
            {"id": pid},
            {"$set": {
                "id": pid,
                "email": f"iter76-pro-{tag}-{i}@refer.io",
                "role": "professional",
                "name": f"Iter76 Pro {i}",
                "profile_complete": True,
                "profile": {
                    "company": "TestCo", "designation": "Engineer",
                    "expertise": ["Python", "System Design"] if i == 0 else ["SQL", "AWS"],
                    "experience_years": 5, "current_location": "Bangalore",
                },
                "credits": 0,
                "created_at": now.isoformat(),
            }},
            upsert=True,
        )
        pros.append(pid)

        # Insert a future available slot for each pro
        slot_start = now + timedelta(days=2, hours=i)
        slot_end = slot_start + timedelta(minutes=30)
        db.interview_slots.update_one(
            {"id": f"iter76-slot-{tag}-{i}"},
            {"$set": {
                "id": f"iter76-slot-{tag}-{i}",
                "pro_id": pid,
                "status": "available",
                "start_at": slot_start.isoformat(),
                "end_at": slot_end.isoformat(),
                "duration_min": 30,
                "topic": topics_by_i[i],
                "skill_set": ["Python"] if topics_by_i[i] == "Technical Discussion" else [],
                "experience_years": 5,
                "created_at": now.isoformat(),
            }},
            upsert=True,
        )

    # Ensure there are >500 profile_complete pros in DB so the old bug would trigger.
    total_complete = db.users.count_documents({"role": "professional", "profile_complete": True})
    if total_complete < 600:
        docs = []
        for i in range(600 - total_complete):
            docs.append({
                "id": f"iter76-noise-{tag}-{i}",
                "email": f"noise-{tag}-{i}@example.com",
                "role": "professional",
                "name": f"Noise {i}",
                "profile_complete": True,
                "profile": {"company": "X", "designation": "Y", "experience_years": 1},
                "credits": 0,
                "created_at": now.isoformat(),
            })
        if docs:
            db.users.insert_many(docs, ordered=False)

    # Student — seed directly + mint a JWT (bypass OTP signup flow)
    sid = f"iter76-stud-{tag}"
    db.users.update_one(
        {"id": sid},
        {"$set": {
            "id": sid,
            "email": f"iter76-stud-{tag}@example.com",
            "role": "student",
            "name": "Iter76 Student",
            "profile_complete": True,
            "profile": {"preferred_role": "fresher"},
            "credits": 1000,
            "created_at": now.isoformat(),
        }},
        upsert=True,
    )
    student_token = _mint_student_token(sid)

    yield {"pros": pros, "student_token": student_token, "tag": tag}

    # cleanup
    db.users.delete_many({"id": {"$regex": f"^iter76-.*{tag}"}})
    db.interview_slots.delete_many({"id": {"$regex": f"^iter76-slot-{tag}"}})


def test_all_pros_with_future_slots_are_returned(scenario, db):
    tok = scenario["student_token"]
    seeded = set(scenario["pros"])
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    returned_ids = {p["id"] for p in r.json()}
    missing = seeded - returned_ids
    assert not missing, (
        f"Expected all seeded pros to appear, but these are missing: {missing}. "
        f"Returned={len(returned_ids)} total."
    )


def test_slots_available_counts_are_correct(scenario):
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()}
    for pid in scenario["pros"]:
        assert pid in by_id, f"Missing {pid}"
        assert by_id[pid]["slots_available"] >= 1
        assert by_id[pid]["slots_total"] >= 1


def test_has_available_slots_false_does_not_use_slot_join(scenario):
    """When ?has_available_slots=false the endpoint should still cap at a
    generous limit and not filter by slot presence."""
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=false",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    assert len(r.json()) >= 3


# ============================================================
# Iter 77 — topic filter must restrict pros to the selected topic
# ============================================================
def test_topic_filter_technical_only_returns_technical_pros(scenario):
    """Pro at index 0 has ONLY a Technical Discussion slot; pros 1 & 2 do not."""
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true&topic=Technical%20Discussion",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    returned = {p["id"] for p in r.json()}
    tech_pro, hr_pro, career_pro = scenario["pros"]
    assert tech_pro in returned, "Technical pro must appear for topic=Technical Discussion"
    assert hr_pro not in returned, "HR pro must NOT appear for topic=Technical Discussion"
    assert career_pro not in returned, "Career pro must NOT appear for topic=Technical Discussion"


def test_topic_filter_hr_only_returns_hr_pros(scenario):
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true&topic=HR%20Discussion",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    returned = {p["id"] for p in r.json()}
    tech_pro, hr_pro, career_pro = scenario["pros"]
    assert hr_pro in returned
    assert tech_pro not in returned
    assert career_pro not in returned


def test_topic_filter_career_only_returns_career_pros(scenario):
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true&topic=Career%20Guidance",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    returned = {p["id"] for p in r.json()}
    tech_pro, hr_pro, career_pro = scenario["pros"]
    assert career_pro in returned
    assert tech_pro not in returned
    assert hr_pro not in returned


def test_topic_filter_no_topic_returns_all(scenario):
    tok = scenario["student_token"]
    r = requests.get(
        f"{BASE_URL}/api/professionals?has_available_slots=true",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    returned = {p["id"] for p in r.json()}
    for pid in scenario["pros"]:
        assert pid in returned

