"""Jobs, Applications & Professionals endpoints — Phase C part 3 refactor.

URLs and behaviour preserved. All shared helpers + Pydantic models are imported
from `server.py` (which continues to own the credit-economy, audit, notification
and DB plumbing so existing tests and other routers keep working unchanged).
"""
import re
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from server import (
    db,
    current_user,
    require_role,
    require_phone_verified,
    new_id,
    now_iso,
    push_notification,
    write_audit,
    expand_city,
    _credit_user,
    _can_use_free,
    get_action_cost,
    JOB_POST_REWARD,
    JOB_POST_REWARD_MIN_APPS,
    OPEN_POSITIONS_OPTIONS,
    JobPostBody,
    JobPatchBody,
    ApplyJobBody,
    ReferBody,
    HireBody,
    ReferOwnJobBody,
    StatusUpdateBody,
)

router = APIRouter()


# ------------------- Professional discovery -------------------
@router.get("/professionals")
async def list_professionals(
    skill: Optional[str] = Query(None, description="Case-insensitive partial match across expertise"),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="fresher | experienced"),
    date: Optional[str] = Query(None, description="YYYY-MM-DD — show only pros with an available slot starting that day"),
    has_available_slots: bool = Query(True, description="Hide pros with no future, available slot"),
    u: dict = Depends(current_user),
):
    pros = await db.users.find({"role": "professional", "profile_complete": True}, {"_id": 0, "password_hash": 0}).to_list(500)
    if skill:
        sk = skill.lower().strip()
        pros = [
            p for p in pros
            if any(sk in (s or "").lower() for s in (p.get("profile", {}).get("expertise", []) or p.get("profile", {}).get("skills", []) or []))
        ]
    if location:
        loc = location.lower().strip()
        pros = [p for p in pros if loc in (p.get("profile", {}).get("current_location") or "").lower()]
    if category in ("fresher", "experienced"):
        def _cat(p):
            y = int(p.get("profile", {}).get("experience_years") or 0)
            return "experienced" if y > 0 else "fresher"
        pros = [p for p in pros if _cat(p) == category]

    if has_available_slots:
        now_dt = datetime.now(timezone.utc)
        slot_q: dict = {"status": {"$in": ["available", "booked"]}}
        slots = await db.interview_slots.find(slot_q, {"_id": 0, "pro_id": 1, "status": 1, "start_at": 1, "skill_set": 1}).to_list(5000)
        agg: dict[str, dict] = {}
        for s in slots:
            try:
                sd = datetime.fromisoformat((s.get("start_at") or "").replace("Z", "+00:00"))
            except Exception:
                continue
            if sd <= now_dt:
                continue
            if date and sd.strftime("%Y-%m-%d") != date:
                continue
            d = agg.setdefault(s["pro_id"], {"total": 0, "available": 0})
            d["total"] += 1
            if s.get("status") == "available":
                d["available"] += 1
        pros = [p for p in pros if p["id"] in agg]
        for p in pros:
            stats = agg.get(p["id"], {"total": 0, "available": 0})
            p["_slots_total"] = stats["total"]
            p["_slots_available"] = stats["available"]

    return [
        {
            "id": p["id"],
            "name": p.get("name") or p["email"].split("@")[0],
            "company": p.get("profile", {}).get("company"),
            "designation": p.get("profile", {}).get("designation"),
            "experience_years": p.get("profile", {}).get("experience_years"),
            "expertise": p.get("profile", {}).get("expertise") or p.get("profile", {}).get("skills", []),
            "current_location": p.get("profile", {}).get("current_location"),
            "rating": float(p.get("rating") or 0),
            "ratings_count": int(p.get("ratings_count") or 0),
            "slots_total": int(p.get("_slots_total") or 0),
            "slots_available": int(p.get("_slots_available") or 0),
            "fully_booked": int(p.get("_slots_total") or 0) > 0 and int(p.get("_slots_available") or 0) == 0,
        }
        for p in pros
    ]


# ------------------- Jobs -------------------
@router.post("/jobs")
async def post_job(body: JobPostBody, u: dict = Depends(require_role(["employer", "professional"]))):
    await require_phone_verified(u)
    if not body.title or len(body.title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job Title is required.")
    if not body.description or len(body.description.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job Description is required.")
    if not body.location or len(body.location.strip()) < 2:
        raise HTTPException(status_code=400, detail="Location is required.")
    if not body.skills_required or len([s for s in body.skills_required if s.strip()]) == 0:
        raise HTTPException(status_code=400, detail="Skill Set is required.")
    profile = u.get("profile", {}) or {}
    default_company = profile.get("company_name") or profile.get("company")
    company_resolved = (body.company or default_company or "").strip()
    if not company_resolved:
        raise HTTPException(status_code=400, detail="Company Name is required.")
    label = body.open_positions_label or "1"
    if label not in OPEN_POSITIONS_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid Number of Open Positions. Allowed: {OPEN_POSITIONS_OPTIONS}")
    if label.endswith("+"):
        openings = body.open_positions or int(label[:-1])
    else:
        openings = body.open_positions or int(label)
    category = body.category or ("experienced" if (body.experience_required or 0) > 0 else "fresher")
    exp_req = body.experience_required or 0
    if category == "experienced" and exp_req <= 0 and not body.experience_min and not body.experience_max:
        raise HTTPException(status_code=400, detail="experience_required must be > 0 for experienced category")
    industry_resolved = (body.industry_type or "").strip()
    if industry_resolved == "__OTHER__":
        if not (body.industry_other or "").strip():
            raise HTTPException(status_code=400, detail="Please specify the industry (Other).")
        industry_resolved = body.industry_other.strip()
    location_resolved = body.location.strip()
    if location_resolved == "__OTHER__":
        if not (body.location_other or "").strip():
            raise HTTPException(status_code=400, detail="Please specify the location (Other).")
        location_resolved = body.location_other.strip()
    exp_min = body.experience_min if body.experience_min is not None else exp_req
    exp_max = body.experience_max if body.experience_max is not None else max(exp_req, exp_min or 0)
    if exp_min is not None and exp_max is not None and exp_max < exp_min:
        raise HTTPException(status_code=400, detail="Maximum experience must be ≥ Minimum experience")

    proof_link = (body.proof_link or "").strip()
    proof_b64 = (body.proof_screenshot_b64 or "").strip()
    proof_mime = (body.proof_screenshot_mime or "").strip().lower()
    if proof_link and not re.match(r"^https?://[^\s]+\.[^\s]+", proof_link):
        raise HTTPException(status_code=400, detail="Please enter a valid Job Opening Link (must start with http:// or https://).")
    if proof_b64 and proof_mime and proof_mime not in {"image/jpeg", "image/jpg", "image/png", "application/pdf"}:
        raise HTTPException(status_code=400, detail="Proof screenshot must be JPG, JPEG, PNG, or PDF.")
    if u["role"] == "professional" and not proof_link and not proof_b64:
        raise HTTPException(
            status_code=400,
            detail="Please provide either a Job Opening Screenshot or a Job Opening Link to verify the position.",
        )

    job = {
        "id": new_id(),
        "employer_id": u["id"],
        "employer_name": company_resolved,
        "posted_by_role": u["role"],
        "posted_by_name": u.get("name") or u["email"].split("@")[0],
        "source": "professional",
        "title": body.title.strip(),
        "company": company_resolved,
        "description": body.description.strip(),
        "location": location_resolved,
        "salary_range": body.salary_range or "",
        "salary_range_label": body.salary_range_label or "",
        "industry_type": industry_resolved,
        "skills_required": [s.strip() for s in body.skills_required if s.strip()],
        "category": category,
        "experience_required": exp_req,
        "experience_min": int(exp_min) if exp_min is not None else None,
        "experience_max": int(exp_max) if exp_max is not None else None,
        "open_positions": openings,
        "open_positions_label": label,
        "bulk_openings": openings,
        "status": "open",
        "proof_screenshot_b64": proof_b64 if proof_b64 else "",
        "proof_screenshot_mime": proof_mime if proof_b64 else "",
        "proof_link": proof_link,
        "verification_status": "pending" if u["role"] == "professional" else "verified",
        "verified_by": "" if u["role"] == "professional" else "system",
        "verified_at": "" if u["role"] == "professional" else now_iso(),
        "verification_note": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.jobs.insert_one(job)
    return {k: v for k, v in job.items() if k != "_id"}


@router.get("/jobs")
async def list_jobs(
    u: dict = Depends(current_user),
    skill: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    exp_min: Optional[str] = Query(None),
    exp_max: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    sort: Optional[Literal["newest", "oldest"]] = Query("newest"),
    mine: bool = Query(False, description="When true (pro/employer), return only jobs posted by the current user"),
    source: Optional[Literal["admin", "professional"]] = Query(None, description="Filter by job source"),
):
    q: dict = {}
    if u["role"] == "employer":
        q["employer_id"] = u["id"]
    elif u["role"] == "professional":
        if mine:
            q["employer_id"] = u["id"]
        else:
            q["$or"] = [
                {"employer_id": u["id"]},
                {"status": "open", "posted_by_role": {"$ne": "professional"}},
                {"status": "open", "posted_by_role": "professional", "verification_status": "verified"},
            ]
    elif u["role"] == "admin":
        pass
    else:
        q["status"] = "open"
        q["$or"] = [
            {"posted_by_role": {"$ne": "professional"}, "source": {"$ne": "admin"}},
            {"posted_by_role": "professional", "verification_status": "verified"},
        ]
    if skill:
        q["skills_required"] = {"$regex": re.escape(skill), "$options": "i"}
    if location:
        synonyms = expand_city(location)
        pattern = "|".join(re.escape(s) for s in synonyms)
        q["location"] = {"$regex": pattern, "$options": "i"}
    if category in ("fresher", "experienced", "intern"):
        q["category"] = category
    if company:
        q["company"] = {"$regex": company, "$options": "i"}
    if industry:
        q["industry_type"] = {"$regex": re.escape(industry), "$options": "i"}
    if source == "admin":
        q = {"source": "admin", "status": "open"}
    elif source == "professional":
        q["source"] = {"$ne": "admin"}

    sort_dir = 1 if sort == "oldest" else -1
    jobs = await db.jobs.find(q, {"_id": 0}).sort("created_at", sort_dir).to_list(500)

    def _parse_exp(val):
        if val is None or val == "":
            return None
        if isinstance(val, str) and val.endswith("+"):
            return int(val[:-1])
        try:
            return int(val)
        except Exception:
            return None
    fmin = _parse_exp(exp_min)
    fmax = _parse_exp(exp_max)
    if fmin is not None or fmax is not None:
        kept = []
        f_max_eff = 999 if (isinstance(exp_max, str) and exp_max.endswith("+")) else fmax
        for j in jobs:
            jmin = j.get("experience_min")
            jmax = j.get("experience_max")
            if jmin is None and jmax is None:
                base = int(j.get("experience_required") or 0)
                jmin, jmax = base, base
            elif jmin is None:
                jmin = 0
            elif jmax is None:
                jmax = 999
            if fmin is not None and jmax < fmin:
                continue
            if f_max_eff is not None and jmin > f_max_eff:
                continue
            kept.append(j)
        jobs = kept

    job_ids = [j["id"] for j in jobs]
    if job_ids:
        agg = await db.applications.aggregate([
            {"$match": {"job_id": {"$in": job_ids}}},
            {"$group": {"_id": {"job": "$job_id", "status": "$status"}, "n": {"$sum": 1}}},
        ]).to_list(2000)
        applied_map: dict[str, int] = {}
        shortlisted_map: dict[str, int] = {}
        for r in agg:
            jid = r["_id"]["job"]
            st = r["_id"]["status"]
            if st in ("withdrawn",):
                continue
            applied_map[jid] = applied_map.get(jid, 0) + r["n"]
            if st in ("shortlisted", "interview_scheduled", "awaiting_interview", "hired"):
                shortlisted_map[jid] = shortlisted_map.get(jid, 0) + r["n"]
        for j in jobs:
            j["applied_count"] = applied_map.get(j["id"], 0)
            j["shortlisted_count"] = shortlisted_map.get(j["id"], 0)
    if u["role"] == "student" and jobs:
        my_apps = await db.applications.find({"student_id": u["id"]}, {"_id": 0, "job_id": 1, "status": 1}).to_list(1000)
        by_job = {a["job_id"]: a["status"] for a in my_apps}
        for j in jobs:
            j["applied"] = j["id"] in by_job
            j["application_status"] = by_job.get(j["id"])
    if u["role"] in ("employer", "professional"):
        for j in jobs:
            if j.get("employer_id") == u["id"]:
                j["applications_count"] = j.get("applied_count", 0)
    return jobs


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, u: dict = Depends(current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] == "student":
        app = await db.applications.find_one({"student_id": u["id"], "job_id": job_id}, {"_id": 0})
        job["applied"] = bool(app)
        job["application_status"] = app["status"] if app else None
    return job


@router.patch("/jobs/{job_id}")
async def edit_job(job_id: str, body: JobPatchBody, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can edit")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "open_positions" in updates:
        updates["bulk_openings"] = updates["open_positions"]
    updates["updated_at"] = now_iso()
    await db.jobs.update_one({"id": job_id}, {"$set": updates})
    out = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return out


@router.post("/jobs/{job_id}/close")
async def close_job(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can close")
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "closed", "updated_at": now_iso()}})
    return {"message": "Closed"}


@router.post("/jobs/{job_id}/reopen")
async def reopen_job(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can reopen")
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "open", "updated_at": now_iso()}})
    return {"message": "Reopened"}


@router.get("/jobs/{job_id}/applicants")
async def job_applicants(job_id: str, u: dict = Depends(require_role(["employer", "professional", "admin"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if u["role"] != "admin" and job["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only owner can view")
    apps = await db.applications.find({"job_id": job_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    student_ids = [a["student_id"] for a in apps]
    students = await db.users.find({"id": {"$in": student_ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    sm = {s["id"]: s for s in students}
    out = []
    for a in apps:
        s = sm.get(a["student_id"], {})
        p = s.get("profile", {}) or {}
        out.append({
            **a,
            "student_profile": {
                "name": s.get("name") or s.get("email", "").split("@")[0],
                "skills": p.get("skills", []),
                "resume_score": p.get("resume_score", 0),
                "current_location": p.get("current_location"),
                "preferred_role": p.get("preferred_role"),
                "years_of_experience": p.get("years_of_experience"),
                "education": p.get("education"),
                "passed_out_year": p.get("passed_out_year"),
            },
        })
    return out


# ------------------- Saved jobs -------------------
@router.post("/jobs/{job_id}/save")
async def save_job(job_id: str, u: dict = Depends(require_role(["student"]))):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    res = await db.saved_jobs.update_one(
        {"student_id": u["id"], "job_id": job_id},
        {"$setOnInsert": {"id": new_id(), "student_id": u["id"], "job_id": job_id, "saved_at": now_iso()}},
        upsert=True,
    )
    return {"saved": True, "first_time": res.upserted_id is not None}


@router.delete("/jobs/{job_id}/save")
async def unsave_job(job_id: str, u: dict = Depends(require_role(["student"]))):
    await db.saved_jobs.delete_one({"student_id": u["id"], "job_id": job_id})
    return {"saved": False}


@router.get("/saved-jobs")
async def list_saved_jobs(u: dict = Depends(require_role(["student"]))):
    saved = await db.saved_jobs.find({"student_id": u["id"]}, {"_id": 0}).sort("saved_at", -1).to_list(500)
    job_ids = [s["job_id"] for s in saved]
    jobs = await db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0}).to_list(500)
    return jobs


# ------------------- Apply / Refer / Applications -------------------
@router.post("/jobs/apply")
async def apply_job(body: ApplyJobBody, u: dict = Depends(require_role(["student"]))):
    job = await db.jobs.find_one({"id": body.job_id}, {"_id": 0})
    if not job or job["status"] != "open":
        raise HTTPException(status_code=400, detail="Job not available")
    if (job.get("source") or "").lower() == "admin":
        raise HTTPException(
            status_code=400,
            detail="This is an Admin Walk-in & Direct Job. Please contact the recruiter directly using the details on the job page — no in-app application needed.",
        )
    existing = await db.applications.find_one({"job_id": job["id"], "student_id": u["id"]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Already applied")
    use_free = _can_use_free(u, "referral")
    per_action_cost = get_action_cost(u)
    if not use_free and u.get("credits", 0) < per_action_cost:
        raise HTTPException(status_code=402, detail="Insufficient credits. Please add credits to continue applying for this job.")
    if use_free:
        await db.users.update_one({"id": u["id"]}, {"$inc": {"free_uses_left": -1}})
        charged = 0
    else:
        await _credit_user(u["id"], -per_action_cost, "job_application", {"job_id": job["id"], "cost": per_action_cost})
        charged = per_action_cost
    app_doc = {
        "id": new_id(),
        "job_id": job["id"],
        "job_title": job["title"],
        "employer_id": job["employer_id"],
        "student_id": u["id"],
        "student_name": u.get("name") or u["email"].split("@")[0],
        "referrer_pro_id": None,
        "status": "applied",
        "status_history": [{"status": "applied", "at": now_iso(), "by": u["id"]}],
        "credits_charged": charged,
        "created_at": now_iso(),
    }
    await db.applications.insert_one(app_doc)
    await push_notification(u["id"], "Application sent ✉️", f"Applied to {job['title']}", "success")
    await push_notification(job["employer_id"], "New applicant", f"For {job['title']}", "info")

    # Pro-poster reward: one-time +JOB_POST_REWARD when the job (posted by a pro) crosses
    # JOB_POST_REWARD_MIN_APPS valid non-withdrawn applications. Idempotent via
    # `posting_reward_paid` flag + conditional update to be race-safe.
    if job.get("posted_by_role") == "professional" and not job.get("posting_reward_paid"):
        valid_count = await db.applications.count_documents({
            "job_id": job["id"],
            "status": {"$nin": ["withdrawn"]},
        })
        if valid_count >= JOB_POST_REWARD_MIN_APPS:
            res = await db.jobs.update_one(
                {"id": job["id"], "posting_reward_paid": {"$ne": True}},
                {"$set": {"posting_reward_paid": True}},
            )
            if res.modified_count == 1:
                await _credit_user(
                    job["employer_id"],
                    JOB_POST_REWARD,
                    "job_post_reward",
                    {"job_id": job["id"], "job_title": job.get("title"), "applications": valid_count},
                )
                await push_notification(
                    job["employer_id"],
                    f"Earned +{JOB_POST_REWARD} credits 💼",
                    f"Your post '{job.get('title')}' crossed {JOB_POST_REWARD_MIN_APPS} applications!",
                    "success",
                )

    return {"message": "Applied", "used_free": use_free}


@router.post("/referrals")
async def refer_student(body: ReferBody, u: dict = Depends(require_role(["professional"]))):
    student = await db.users.find_one({"id": body.student_id, "role": "student"}, {"_id": 0})
    job = await db.jobs.find_one({"id": body.job_id, "status": "open"}, {"_id": 0})
    if not student or not job:
        raise HTTPException(status_code=400, detail="Student or job not found")
    existing = await db.applications.find_one({"job_id": job["id"], "student_id": student["id"]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Application already exists")
    app_doc = {
        "id": new_id(),
        "job_id": job["id"],
        "job_title": job["title"],
        "employer_id": job["employer_id"],
        "student_id": student["id"],
        "student_name": student.get("name") or student["email"].split("@")[0],
        "referrer_pro_id": u["id"],
        "referrer_pro_name": u.get("name") or u["email"].split("@")[0],
        "note": body.note,
        "status": "referred",
        "created_at": now_iso(),
    }
    await db.applications.insert_one(app_doc)
    await db.users.update_one({"id": u["id"]}, {"$inc": {"referrals_made": 1}})
    await push_notification(student["id"], "You've been referred 🌟", f"{u.get('name') or 'A professional'} referred you for {job['title']}", "success")
    await push_notification(job["employer_id"], "New referral", f"For {job['title']}", "info")
    return {"message": "Referral created", "application_id": app_doc["id"]}


@router.get("/applications")
async def list_applications(u: dict = Depends(current_user)):
    if u["role"] == "student":
        q = {"student_id": u["id"]}
    elif u["role"] == "employer":
        q = {"employer_id": u["id"]}
    elif u["role"] == "professional":
        q = {"referrer_pro_id": u["id"]}
    else:
        q = {}
    apps = await db.applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    if u["role"] == "student" and apps:
        job_ids = list({a["job_id"] for a in apps if a.get("job_id")})
        jobs = await db.jobs.find(
            {"id": {"$in": job_ids}},
            {"_id": 0, "id": 1, "company": 1, "location": 1, "title": 1, "employer_name": 1},
        ).to_list(1000)
        jm = {j["id"]: j for j in jobs}
        for a in apps:
            j = jm.get(a.get("job_id")) or {}
            a["company"] = a.get("company") or j.get("company") or j.get("employer_name") or ""
            a["location"] = a.get("location") or j.get("location") or ""
    return apps


@router.get("/applications/pool")
async def applications_pool(_: dict = Depends(require_role(["professional"]))):
    """All applicants across the platform — pros browse to refer candidates."""
    apps = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    student_ids = list({a["student_id"] for a in apps})
    students = await db.users.find(
        {"id": {"$in": student_ids}},
        {"_id": 0, "password_hash": 0},
    ).to_list(1000)
    sm = {s["id"]: s for s in students}
    out = []
    for a in apps:
        s = sm.get(a["student_id"], {})
        profile = s.get("profile", {}) or {}
        out.append({
            **a,
            "student_profile": {
                "education": profile.get("education"),
                "education_details": profile.get("education_details"),
                "passed_out_year": profile.get("passed_out_year"),
                "current_location": profile.get("current_location"),
                "preferred_role": profile.get("preferred_role"),
                "years_of_experience": profile.get("years_of_experience"),
                "skills": profile.get("skills", []),
                "resume_score": profile.get("resume_score", 0),
                "resume_filename": profile.get("resume_filename"),
                "resume_link": profile.get("resume_link"),
            },
            "interviews_attended": s.get("interviews_attended", 0),
        })
    return out


@router.post("/applications/hire")
async def hire_candidate(body: HireBody, u: dict = Depends(require_role(["employer", "professional"]))):
    """Mark a candidate as hired. Goes to 'hired_pending' until admin approves and
    the +HIRING_REWARD credits go to the job poster after admin approval."""
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    if appdoc["employer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only the job poster can mark this candidate hired")
    if appdoc["status"] in ("hired", "hired_pending"):
        raise HTTPException(status_code=400, detail="Already submitted for hire approval")
    if not body.proof_base64 and not body.note:
        raise HTTPException(status_code=400, detail="Please attach supporting evidence or a note")
    change = {
        "id": new_id(),
        "application_id": body.application_id,
        "requested_by_id": u["id"],
        "requested_by_role": u["role"],
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": "hired",
        "proof_base64": body.proof_base64,
        "proof_filename": body.proof_filename,
        "proof_mime_type": body.proof_mime_type,
        "note": body.note or "",
        "status": "pending",
        "admin_note": "",
        "created_at": now_iso(),
    }
    await db.status_changes.insert_one(change)
    await db.applications.update_one(
        {"id": body.application_id},
        {"$set": {"status": "hired_pending", "hired_pending_at": now_iso()}},
    )
    await push_notification(u["id"], "Hire submitted for admin review ⏳", "We'll credit you 1500 once approved.", "info")
    await push_notification(appdoc["student_id"], "Hire submitted 🎉", f"For {appdoc['job_title']} — pending admin verification.", "info")
    return {"message": "Submitted for admin verification", "change_id": change["id"]}


@router.post("/applications/refer-own")
async def refer_own_applicant(body: ReferOwnJobBody, u: dict = Depends(require_role(["professional"]))):
    """Pro who posted the job refers an applicant directly (applied → shortlisted → referred in one shot)."""
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    job = await db.jobs.find_one({"id": appdoc["job_id"]}, {"_id": 0})
    if not job or job.get("employer_id") != u["id"] or job.get("posted_by_role") != "professional":
        raise HTTPException(status_code=403, detail="Only the posting professional can refer this candidate")
    if appdoc["status"] in ("referred", "hired", "hired_pending"):
        return {"message": "Already referred", "status": appdoc["status"]}
    hist = list(appdoc.get("status_history") or [])
    for st in ("shortlisted", "referred"):
        hist.append({"status": st, "at": now_iso(), "by": u["id"], "note": body.note or ""})
    await db.applications.update_one(
        {"id": appdoc["id"]},
        {"$set": {
            "status": "referred",
            "status_history": hist,
            "referrer_pro_id": u["id"],
            "referrer_pro_name": u.get("name") or u["email"].split("@")[0],
            "referral_note": body.note or "",
        }},
    )
    await db.users.update_one({"id": u["id"]}, {"$inc": {"referrals_made": 1}})
    await push_notification(appdoc["student_id"], "You've been referred 🌟", f"For {appdoc['job_title']}", "success")
    await push_notification(u["id"], "Referral submitted ✅", f"For {appdoc['job_title']}", "success")
    await db.status_changes.insert_one({
        "id": new_id(),
        "application_id": appdoc["id"],
        "requested_by_id": u["id"],
        "requested_by_role": "professional",
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": "referred",
        "note": body.note or "",
        "status": "approved",
        "auto": True,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return {"message": "Referred", "application_id": appdoc["id"]}


# ------------------- Status pipeline (Applied → Hired) -------------------
@router.post("/applications/status")
async def request_status_change(body: StatusUpdateBody, u: dict = Depends(current_user)):
    appdoc = await db.applications.find_one({"id": body.application_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    is_owner_student = (u["role"] == "student" and appdoc["student_id"] == u["id"])
    is_employer = (u["role"] == "employer" and appdoc["employer_id"] == u["id"])
    is_referrer = (u["role"] == "professional" and appdoc.get("referrer_pro_id") == u["id"])
    if not (is_owner_student or is_employer or is_referrer or u["role"] == "admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    change = {
        "id": new_id(),
        "application_id": body.application_id,
        "requested_by_id": u["id"],
        "requested_by_role": u["role"],
        "requested_by_name": u.get("name") or u["email"].split("@")[0],
        "from_status": appdoc["status"],
        "to_status": body.new_status,
        "proof_base64": body.proof_base64,
        "proof_filename": body.proof_filename,
        "proof_mime_type": body.proof_mime_type,
        "note": body.note or "",
        "status": "pending",
        "admin_note": "",
        "created_at": now_iso(),
    }
    await db.status_changes.insert_one(change)
    await push_notification(u["id"], "Status update submitted", "Pending admin review.", "info")
    return {"message": "Submitted for admin review", "change_id": change["id"], "status": "pending"}


@router.get("/applications/{app_id}/timeline")
async def application_timeline(app_id: str, u: dict = Depends(current_user)):
    appdoc = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Application not found")
    history = appdoc.get("status_history", [])
    pending = await db.status_changes.find(
        {"application_id": app_id, "status": "pending"}, {"_id": 0, "proof_base64": 0}
    ).sort("created_at", -1).to_list(50)
    return {
        "current_status": appdoc["status"],
        "history": history,
        "pending_changes": pending,
    }


# ------------------- Job resubmit (Pro) -------------------
@router.post("/jobs/{job_id}/resubmit")
async def resubmit_job(job_id: str, u: dict = Depends(require_role(["professional"]))):
    """Pro resubmits a rejected job for fresh admin review — status flips back to pending."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("employer_id") != u["id"]:
        raise HTTPException(status_code=403, detail="You can only resubmit your own jobs.")
    if job.get("verification_status") != "rejected":
        raise HTTPException(status_code=400, detail="Only rejected jobs can be resubmitted.")
    now = now_iso()
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "verification_status": "pending",
            "verification_note": "",
            "verified_by": "",
            "verified_at": "",
            "updated_at": now,
        }},
    )
    await write_audit(
        u, "job.resubmit", "job", job_id,
        before={"verification_status": "rejected"},
        after={"verification_status": "pending"},
        reason="Pro resubmitted for review",
        extra={"job_title": job.get("title", "")},
    )
    return {"ok": True, "verification_status": "pending"}
