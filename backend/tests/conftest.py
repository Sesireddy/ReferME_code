"""Shared pytest fixtures for ReferME backend tests."""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE_URL:
    # fallback to frontend/.env
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe_env.read_text().splitlines():
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def api_url():
    return API


@pytest.fixture()
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _signup_verify(session, role: str, prefix: str = "TEST"):
    email = f"{prefix.lower()}_{role}_{uuid.uuid4().hex[:8]}@referme.io"
    password = "Test@12345"
    r = session.post(f"{API}/auth/signup", json={"email": email, "password": password, "role": role, "name": f"{prefix} {role}"})
    assert r.status_code == 200, r.text
    otp = r.json().get("mock_otp")
    assert otp, "mock_otp must be present in mock mode"
    r2 = session.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    return {"email": email, "password": password, "token": data["token"], "user": data["user"]}


def _gmail_verify_in_db(user_id: str):
    """Test helper — flip gmail_verified for a pro in DB so they can post slots without OTP flow."""
    from pymongo import MongoClient
    mc = MongoClient(os.environ["MONGO_URL"])
    mc[os.environ["DB_NAME"]].users.update_one(
        {"id": user_id},
        {"$set": {"gmail_verified": True, "alternate_gmail": f"test.pro.{user_id[:6]}@gmail.com"}},
    )
    mc.close()


@pytest.fixture()
def student(session):
    return _signup_verify(session, "student")


@pytest.fixture()
def professional(session):
    """Default 'professional' fixture for tests that just want to post slots/jobs.
    Use _signup_verify directly when you need a raw, un-gmail-verified pro.
    """
    pro = _signup_verify(session, "professional")
    _gmail_verify_in_db(pro["user"]["id"])
    return pro


@pytest.fixture()
def employer(session):
    # Employer signup is intentionally blocked in production (see /auth/signup), but
    # tests still need an employer user to validate job-posting flows. Create one
    # directly in the DB to bypass the block. Hash matches the format produced by
    # server.hash_password (passlib bcrypt).
    from pymongo import MongoClient
    from passlib.context import CryptContext
    eid = uuid.uuid4().hex
    email = f"test_employer_{eid[:8]}@referme.io"
    password = "Test@12345"
    pw_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)
    mc = MongoClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    user_doc = {
        "id": eid,
        "email": email,
        "role": "employer",
        "name": f"TEST employer",
        "password_hash": pw_hash,
        "is_email_verified": True,
        "credits": 0,
        "profile_complete": True,
        "profile": {"company_name": f"Acme {eid[:6]}"},
        "free_uses_left": 2,
        "created_at": "2025-01-01T00:00:00+00:00",
    }
    db.users.insert_one(user_doc)
    mc.close()
    # Log in to obtain token via the normal endpoint
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": password, "token": data["token"], "user": data["user"]}


@pytest.fixture()
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
