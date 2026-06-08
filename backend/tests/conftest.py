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
    return _signup_verify(session, "employer")


@pytest.fixture()
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"email": "admin@referme.app", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
