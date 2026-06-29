"""Seed iter41 UI test scenario:
- Pro slot, booked, start_at 2h ago, end_at 1h ago -> Done button enabled
Outputs /tmp/iter41_seed.json with pro token + booked past slot id.
"""
import os
import uuid
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))

fe_env = Path("/app/frontend/.env").read_text()
BASE = next(l.split("=", 1)[1].strip() for l in fe_env.splitlines() if l.startswith("EXPO_PUBLIC_BACKEND_URL="))
API = BASE.rstrip("/") + "/api"
MONGO = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def signup(role, prefix):
    email = f"iter41ui_{prefix}_{uuid.uuid4().hex[:8]}@{'acmecorp.io' if role=='professional' else 'example.com'}"
    pw = "Test@12345"
    s = requests.Session()
    r = s.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"iter41ui {prefix}"})
    r.raise_for_status()
    otp = r.json()["mock_otp"]
    r2 = s.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    r2.raise_for_status()
    data = r2.json()
    return {"email": email, "password": pw, "token": data["token"], "user": data["user"]}


def main():
    MONGO.interview_slots.delete_many({"_test_marker": "iter41_ui"})
    pro = signup("professional", "pro")
    stu = signup("student", "stu")
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=2)
    end = now - timedelta(hours=1)
    sid = uuid.uuid4().hex
    doc = {
        "id": sid,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro["user"]["id"],
        "pro_name": pro["user"]["name"],
        "start_at": iso(start),
        "end_at": iso(end),
        "scheduled_at": iso(start),
        "skill_set": ["iter41_past"],
        "experience_years": 2,
        "topic": "iter41 past booked",
        "status": "booked",
        "student_id": stu["user"]["id"],
        "student_name": stu["user"]["name"],
        "student_email": stu["email"],
        "meeting_url": f"https://meet.example.com/iter41-{sid[:8]}",
        "booked_at": iso(now - timedelta(hours=3)),
        "created_at": iso(now - timedelta(hours=4)),
        "_test_marker": "iter41_ui",
    }
    MONGO.interview_slots.insert_one(doc)
    out = {"BASE_URL": BASE, "pro": pro, "student": stu, "slot_id": sid}
    Path("/tmp/iter41_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
