"""Seed 4 scenarios for iter38 student-side UI testing.

Run once before starting Playwright. Prints student token + URL ready for
localStorage injection.
"""
import os
import sys
import uuid
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))

# Read backend URL from frontend .env (public ingress)
fe_env = Path("/app/frontend/.env").read_text()
BASE = next(l.split("=", 1)[1].strip() for l in fe_env.splitlines() if l.startswith("EXPO_PUBLIC_BACKEND_URL="))
API = BASE.rstrip("/") + "/api"
MONGO = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def signup(role, prefix):
    email = f"iter38ui_{prefix}_{uuid.uuid4().hex[:8]}@{'acmecorp.io' if role=='professional' else 'example.com'}"
    pw = "Test@12345"
    s = requests.Session()
    r = s.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"iter38ui {prefix}"})
    r.raise_for_status()
    otp = r.json()["mock_otp"]
    r2 = s.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    r2.raise_for_status()
    data = r2.json()
    return {"email": email, "password": pw, "token": data["token"], "user": data["user"]}


def clean_old():
    MONGO.interview_slots.delete_many({"_test_marker": "iter38_ui"})


def seed_slot(*, pro, stu, start, end, status="booked", joined_by=None, feedback=None, rating=None, label=""):
    sid = uuid.uuid4().hex
    doc = {
        "id": sid,
        "session_id": uuid.uuid4().hex,
        "pro_id": pro["user"]["id"],
        "pro_name": pro["user"]["name"],
        "start_at": iso(start),
        "end_at": iso(end),
        "scheduled_at": iso(start),
        "skill_set": [f"iter38_{label}"],
        "experience_years": 2,
        "topic": f"iter38 {label}",
        "status": status,
        "student_id": stu["user"]["id"],
        "student_name": stu["user"]["name"],
        "student_email": stu["email"],
        "meeting_url": f"https://meet.example.com/iter38ui-{sid[:8]}",
        "booked_at": iso(datetime.now(timezone.utc)),
        "created_at": iso(datetime.now(timezone.utc)),
        "_test_marker": "iter38_ui",
    }
    if joined_by is not None:
        doc["joined_by"] = joined_by
    if feedback is not None:
        doc["feedback"] = feedback
    if rating is not None:
        doc["candidate_rating"] = rating
    MONGO.interview_slots.insert_one(doc)
    return sid


def main():
    clean_old()
    pro = signup("professional", "pro")
    stu = signup("student", "stu")
    now = datetime.now(timezone.utc)

    a = seed_slot(pro=pro, stu=stu, start=now + timedelta(hours=2), end=now + timedelta(hours=2, minutes=30),
                  status="booked", label="A_future")
    b = seed_slot(pro=pro, stu=stu, start=now - timedelta(hours=2), end=now - timedelta(hours=1, minutes=30),
                  status="completed",
                  joined_by=[pro["user"]["id"], stu["user"]["id"]],
                  feedback="Solid DSA fundamentals; communication clear; deepen system-design tradeoffs.",
                  rating=8, label="B_completed_feedback")
    c = seed_slot(pro=pro, stu=stu, start=now - timedelta(minutes=90), end=now - timedelta(minutes=60),
                  status="booked",
                  joined_by=[pro["user"]["id"], stu["user"]["id"]],
                  label="C_past_both_joined_no_complete")
    d = seed_slot(pro=pro, stu=stu, start=now - timedelta(minutes=90), end=now - timedelta(minutes=60),
                  status="booked",
                  joined_by=[pro["user"]["id"]],
                  label="D_no_show")

    out = {
        "BASE_URL": BASE,
        "student": stu,
        "pro": pro,
        "scenarios": {"A": a, "B": b, "C": c, "D": d},
    }
    Path("/tmp/iter38_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
