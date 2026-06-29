"""Seed iter42 UI scenario: create a professional and a student each with a SAVED profile so
their /professional/profile and /student/profile pages open in read-only mode.

Outputs /tmp/iter42_seed.json with tokens + emails.
"""
import os, uuid, json, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("/app/backend/.env"))

fe_env = Path("/app/frontend/.env").read_text()
BASE = next(l.split("=", 1)[1].strip() for l in fe_env.splitlines() if l.startswith("EXPO_PUBLIC_BACKEND_URL="))
API = BASE.rstrip("/") + "/api"


def signup(role, prefix, domain):
    email = f"iter42ui_{prefix}_{uuid.uuid4().hex[:8]}@{domain}"
    pw = "Test@12345"
    s = requests.Session()
    r = s.post(f"{API}/auth/signup", json={"email": email, "password": pw, "role": role, "name": f"iter42 {prefix.title()}"})
    r.raise_for_status()
    otp = r.json()["mock_otp"]
    r2 = s.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp, "purpose": "verify_email"})
    r2.raise_for_status()
    data = r2.json()
    return {"email": email, "password": pw, "token": data["token"], "user": data["user"], "session": s}


def save_pro_profile(sess, token):
    payload = {
        "name": "Iter42 Pro Tester",
        "phone": "9876512345",
        "phone_verified": True,
        "alternate_gmail": f"iter42pro_{uuid.uuid4().hex[:6]}@gmail.com",
        "gender": "male",
        "education": "Bachelor's",
        "company": "Broadridge",
        "designation": "Senior Software Engineer",
        "experience_years": 5,
        "location": "Bengaluru",
        "skills": ["React", "Node", "System Design"],
        "expertise": ["React", "Node", "System Design"],
    }
    r = sess.put(f"{API}/profile", json=payload, headers={"Authorization": f"Bearer {token}"})
    print("PRO save", r.status_code, r.text[:160])
    r.raise_for_status()


def save_stu_profile(sess, token):
    payload = {
        "name": "Iter42 Stu Tester",
        "phone": "9876509876",
        "phone_verified": True,
        "gender": "female",
        "dob": "2001-05-12",
        "education": "Bachelor's",
        "education_details": "B.Tech CSE",
        "passed_out_year": 2023,
        "preferred_role": "experienced",
        "location": "Hyderabad",
        "skills": ["Python", "ML", "FastAPI"],
        "resume_headline": "Aspiring SDE with ML interests",
        "experience_years": 1,
        "company": "Infosys",
        "designation": "Associate Engineer",
        "currently_working": "no",
        "annual_salary": "5-10",
        "notice_period": "1m",
    }
    r = sess.put(f"{API}/profile", json=payload, headers={"Authorization": f"Bearer {token}"})
    print("STU save", r.status_code, r.text[:300])
    r.raise_for_status()


def main():
    pro = signup("professional", "pro", "acmecorp.io")
    save_pro_profile(pro["session"], pro["token"])
    stu = signup("student", "stu", "example.com")
    save_stu_profile(stu["session"], stu["token"])
    out = {
        "BASE_URL": BASE,
        "pro": {k: pro[k] for k in ("email", "password", "token", "user")},
        "student": {k: stu[k] for k in ("email", "password", "token", "user")},
    }
    Path("/tmp/iter42_seed.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
