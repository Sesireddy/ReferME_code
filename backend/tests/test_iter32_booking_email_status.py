"""Iter 32 — verify booking DB record persists email_status='sent' for both
student and pro after the Resend throttle fix. Re-runs the booking happy path
end-to-end and asserts the booking doc fields directly via Mongo.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(os.environ["MONGO_URL"])
    yield cli[os.environ["DB_NAME"]]
    cli.close()


def _signup_verify(http, email, role, name):
    r = http.post(f"{API}/auth/signup", json={"email": email, "password": "Test@12345", "role": role, "name": name})
    assert r.status_code == 200, r.text
    otp = r.json()["mock_otp"]
    r2 = http.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    assert r2.status_code == 200, r2.text
    return r2.json()["token"], r2.json()["user"]["id"]


def test_booking_record_has_both_email_status_sent(http, mongo):
    pro_email = f"test_pro_iter32_{uuid.uuid4().hex[:6]}@acmecorp.io"
    pro_token, pro_id = _signup_verify(http, pro_email, "professional", "TEST Pro32")

    # bypass phone & gmail gates via direct DB write (same shortcut as iter31 suite)
    mongo.users.update_one(
        {"id": pro_id},
        {"$set": {
            "gmail_verified": True,
            "alternate_gmail": f"test.pro.{pro_id[:6]}@gmail.com",
            "profile.phone_verified": True,
            "profile.phone_verified_at": datetime.now(timezone.utc).isoformat(),
            "profile.phone": "+919999900001",
        }},
    )

    start = (datetime.now(timezone.utc) + timedelta(days=3, hours=4)).replace(microsecond=0, second=0)
    end = start + timedelta(minutes=30)
    r = http.post(
        f"{API}/interviews/slots",
        json={
            "start_at": start.isoformat().replace("+00:00", "Z"),
            "end_at": end.isoformat().replace("+00:00", "Z"),
            "skill_set": ["python"],
            "experience_years": 3,
            "topic": "Backend",
        },
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert r.status_code == 200, r.text
    slot_id = r.json()["id"]

    stu_email = f"test_stu_iter32_{uuid.uuid4().hex[:6]}@resend.dev"
    stu_token, stu_id = _signup_verify(http, stu_email, "student", "TEST Stu32")

    rb = http.post(
        f"{API}/interviews/book",
        json={"slot_id": slot_id},
        headers={"Authorization": f"Bearer {stu_token}"},
    )
    assert rb.status_code == 200, rb.text
    booking_id = rb.json().get("id") or rb.json().get("booking_id")

    # Find booking doc in DB
    doc = mongo.interview_bookings.find_one({"pro_id": pro_id, "student_id": stu_id})
    assert doc is not None, "booking record not persisted"
    assert doc.get("student_email_status") == "sent", (
        f"student_email_status expected 'sent', got {doc.get('student_email_status')!r}"
    )
    assert doc.get("pro_email_status") == "sent", (
        f"pro_email_status expected 'sent', got {doc.get('pro_email_status')!r}"
    )

    # cleanup
    mongo.interview_slots.delete_many({"pro_id": pro_id})
    mongo.interview_bookings.delete_many({"pro_id": pro_id})
    mongo.users.delete_one({"id": pro_id})
    mongo.users.delete_one({"id": stu_id})
