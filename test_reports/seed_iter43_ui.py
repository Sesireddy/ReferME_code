"""Seed iter43 UI scenario:
1) Create a student + a pro
2) Pro creates slot, then we backdate it in Mongo so /complete can be called
3) Student books it
4) Pro completes with rating + feedback + proof
5) Then seed an extra "edge" slot for the same student with status=completed, feedback=None,
   candidate_rating=None to test the disabled "Completed" fallback path
6) Also seed a "no-show" past slot for the same student (status=booked, only pro joined)

Outputs /tmp/iter43_seed.json with tokens + slot IDs.
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
    email = f"iter43ui_{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    s = requests.Session()
    r = s.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"iter43 {prefix.title()}"})
    r.raise_for_status()
    otp = r.json()["mock_otp"]
    r2 = s.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    r2.raise_for_status()
    data = r2.json()
    return {"email": email, "password": pw, "token": data["token"], "user": data["user"], "session": s}


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
        "topic": "iter43 UI scenario",
        "status": status,
        "student_id": student_id, "student_name": student_name,
        "student_email": f"{student_name}@example.com",
        "meeting_url": f"https://meet.jit.si/iter43-{sid[:8]}",
        "booked_at": iso(datetime.now(timezone.utc)),
        "created_at": iso(datetime.now(timezone.utc)),
        "_test_marker": "iter43_ui",
    }
    if joined_by is not None: doc["joined_by"] = list(joined_by)
    if feedback is not None: doc["feedback"] = feedback
    if candidate_rating is not None: doc["candidate_rating"] = candidate_rating
    if candidate_feedback is not None: doc["candidate_feedback"] = candidate_feedback
    mongo.interview_slots.insert_one(doc)
    return sid


def main():
    # cleanup any old iter43_ui slots
    mongo.interview_slots.delete_many({"_test_marker": "iter43_ui"})

    pro = signup("professional", "pro", "acmecorp.io")
    stu = signup("student", "stu", "example.com")

    now = datetime.now(timezone.utc)

    # Scenario A: completed slot WITH feedback + rating (BOTH joined_by empty, simulating legacy)
    # Per request: should show green "Reviewed" pill + green "View feedback" button
    slot_completed_with_feedback = seed_slot(
        pro_id=pro["user"]["id"], pro_name="Iter43 Pro",
        student_id=stu["user"]["id"], student_name="Iter43 Stu",
        start_at=now - timedelta(hours=2), end_at=now - timedelta(hours=1, minutes=30),
        status="completed",
        joined_by=[],  # legacy slot — empty joined_by
        feedback="Solid SQL fundamentals. Good clarity on joins and indexes. Needs work on advanced PL/SQL stored procedures and exception handling.",
        candidate_feedback="Solid SQL fundamentals. Good clarity on joins and indexes. Needs work on advanced PL/SQL stored procedures and exception handling.",
        candidate_rating=8,
    )

    # Scenario B: completed BUT no feedback/rating (edge case → should still show disabled "Completed" button)
    slot_completed_no_feedback = seed_slot(
        pro_id=pro["user"]["id"], pro_name="Iter43 Pro",
        student_id=stu["user"]["id"], student_name="Iter43 Stu",
        start_at=now - timedelta(hours=4), end_at=now - timedelta(hours=3, minutes=30),
        status="completed",
        joined_by=[],
        feedback=None,
        candidate_rating=None,
    )

    # Scenario C: no-show — status=booked, past slot, only pro joined
    slot_no_show = seed_slot(
        pro_id=pro["user"]["id"], pro_name="Iter43 Pro",
        student_id=stu["user"]["id"], student_name="Iter43 Stu",
        start_at=now - timedelta(hours=6), end_at=now - timedelta(hours=5, minutes=30),
        status="booked",
        joined_by=[pro["user"]["id"]],  # only pro joined → no-show
    )

    out = {
        "BASE_URL": BASE,
        "pro": {k: pro[k] for k in ("email", "password", "token", "user")},
        "student": {k: stu[k] for k in ("email", "password", "token", "user")},
        "slots": {
            "completed_with_feedback": slot_completed_with_feedback,
            "completed_no_feedback": slot_completed_no_feedback,
            "no_show": slot_no_show,
        },
    }
    Path("/tmp/iter43_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
