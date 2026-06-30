"""Seed iter43b UI retest:
Same scenarios A/B/C as seed_iter43_ui.py, but scenario A intentionally seeds
ONLY `candidate_feedback` (NOT `feedback`) — to truly exercise the new BE alias
inside GET /api/interviews/my-bookings.

If the alias works:
  - The 'View feedback' panel on /student/my-mock-interviews must show the
    full Professional Feedback paragraph (NOT the italic
    'No written feedback was provided.' fallback).

Outputs /tmp/iter43b_seed.json.
"""
import os, uuid, json, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path("/app/backend/.env"))

fe_env = Path("/app/frontend/.env").read_text()
BASE = next(l.split("=", 1)[1].strip() for l in fe_env.splitlines() if l.startswith("EXPO_PUBLIC_BACKEND_URL="))
API = BASE.rstrip("/") + "/api"

mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def signup(role, prefix, domain):
    email = f"iter43b_{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    s = requests.Session()
    r = s.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"iter43b {prefix.title()}"})
    r.raise_for_status()
    otp = r.json()["mock_otp"]
    r2 = s.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    r2.raise_for_status()
    data = r2.json()
    return {"email": email, "password": pw, "token": data["token"], "user": data["user"]}


def seed_slot(*, pro_id, pro_name, student_id, student_name, start_at, end_at,
              status="booked", joined_by=None, feedback=None, candidate_rating=None,
              candidate_feedback=None):
    sid = uuid.uuid4().hex
    doc = {
        "id": sid, "session_id": uuid.uuid4().hex,
        "pro_id": pro_id, "pro_name": pro_name,
        "start_at": iso(start_at), "end_at": iso(end_at),
        "scheduled_at": iso(start_at),
        "skill_set": ["sql", "plsql"], "experience_years": 5,
        "topic": "iter43b retest",
        "status": status,
        "student_id": student_id, "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.jit.si/iter43b-{sid[:8]}",
        "booked_at": iso(datetime.now(timezone.utc)),
        "created_at": iso(datetime.now(timezone.utc)),
        "_test_marker": "iter43b_ui",
    }
    if joined_by is not None: doc["joined_by"] = list(joined_by)
    if feedback is not None: doc["feedback"] = feedback
    if candidate_rating is not None: doc["candidate_rating"] = candidate_rating
    if candidate_feedback is not None: doc["candidate_feedback"] = candidate_feedback
    mongo.interview_slots.insert_one(doc)
    return sid


PROF_FEEDBACK = (
    "Solid SQL fundamentals. Good clarity on joins and indexes. "
    "Needs work on advanced PL/SQL stored procedures and exception handling."
)


def main():
    mongo.interview_slots.delete_many({"_test_marker": "iter43b_ui"})

    pro = signup("professional", "pro", "acmecorp.io")
    stu = signup("student", "stu", "example.com")

    now = datetime.now(timezone.utc)

    # Scenario A: completed slot with ONLY candidate_feedback set (no `feedback` key).
    # This is the exact shape /complete writes — if BE alias is correct, FE will
    # render the feedback text.
    slot_A = seed_slot(
        pro_id=pro["user"]["id"], pro_name="Iter43b Pro",
        student_id=stu["user"]["id"], student_name="Iter43bStu",
        start_at=now - timedelta(hours=2), end_at=now - timedelta(hours=1, minutes=30),
        status="completed",
        joined_by=[],
        feedback=None,                       # explicitly NOT set
        candidate_feedback=PROF_FEEDBACK,    # ONLY this key
        candidate_rating=8,
    )

    # Scenario B: completed with rating but truly no feedback text (panel should still
    # render the rating chip + the italic fallback).
    slot_B = seed_slot(
        pro_id=pro["user"]["id"], pro_name="Iter43b Pro",
        student_id=stu["user"]["id"], student_name="Iter43bStu",
        start_at=now - timedelta(hours=4), end_at=now - timedelta(hours=3, minutes=30),
        status="completed",
        joined_by=[],
        feedback=None,
        candidate_feedback=None,
        candidate_rating=8,
    )

    out = {
        "BASE_URL": BASE,
        "pro": {k: pro[k] for k in ("email", "password", "token", "user")},
        "student": {k: stu[k] for k in ("email", "password", "token", "user")},
        "slots": {
            "completed_only_candidate_feedback": slot_A,
            "completed_rating_no_feedback": slot_B,
        },
        "expected_feedback_text": PROF_FEEDBACK,
    }
    Path("/tmp/iter43b_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
