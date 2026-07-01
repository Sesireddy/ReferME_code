"""Admin Job Postings — Walk-in & Direct Jobs.

Admin-posted jobs are:
- Auto-verified (no approval flow).
- Free for Job Seekers (no credit deduction, no wallet gating, no apply flow).
- Surfaced under a dedicated "Walk-in & Direct Jobs" section on the Job Seeker home.

Endpoints (all admin-only unless noted):
  POST   /api/admin/jobs                       - create a new job (published or draft).
  GET    /api/admin/jobs/mine                  - list jobs authored by the current admin (drafts + published).
  PATCH  /api/admin/jobs/{job_id}              - edit an admin job.
  POST   /api/admin/jobs/{job_id}/publish      - promote a draft to published.
  DELETE /api/admin/jobs/{job_id}              - delete an admin job (exists in server.py already).
"""
import logging
import re
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server import db, admin_only, new_id, now_iso, write_audit

router = APIRouter()
logger = logging.getLogger(__name__)


class AdminJobBody(BaseModel):
    """Payload for admin-created jobs.

    Required: company, title, description, location, skills_required.
    Optional: employment_type, salary_range, walk_in_date/time, venue,
              contact_*, application_deadline, company_logo_b64, category, industry.
    Status: 'draft' saves without publishing; anything else publishes immediately.
    """
    # Required
    company: str = Field(..., min_length=2, max_length=120)
    title: str = Field(..., min_length=2, max_length=140)
    description: str = Field(..., min_length=10)
    location: str = Field(..., min_length=2, max_length=120)
    skills_required: List[str] = Field(..., min_length=1)
    # Optional experience
    experience_min: Optional[int] = Field(default=0, ge=0, le=50)
    experience_max: Optional[int] = Field(default=None, ge=0, le=50)
    open_positions: int = Field(default=1, ge=1, le=9999)
    employment_type: Optional[str] = Field(default="Full-time")  # Full-time / Part-time / Internship / Contract / Walk-in Drive
    salary_range: Optional[str] = ""
    industry_type: Optional[str] = ""
    category: Optional[str] = ""  # fresher / experienced / intern
    # Walk-in / direct
    walk_in_date: Optional[str] = ""  # ISO date string yyyy-mm-dd (frontend picker)
    walk_in_time: Optional[str] = ""  # freeform e.g. "10:00 AM - 4:00 PM"
    venue: Optional[str] = ""
    contact_person: Optional[str] = ""
    contact_number: Optional[str] = ""  # 10-digit Indian
    contact_email: Optional[str] = ""
    application_deadline: Optional[str] = ""  # ISO date
    company_logo_b64: Optional[str] = ""  # data URL or raw base64
    company_logo_mime: Optional[str] = ""
    # 'draft' | 'open' (default open when publishing)
    status: Optional[str] = "open"


class AdminJobPatchBody(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    skills_required: Optional[List[str]] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    open_positions: Optional[int] = None
    employment_type: Optional[str] = None
    salary_range: Optional[str] = None
    industry_type: Optional[str] = None
    category: Optional[str] = None
    walk_in_date: Optional[str] = None
    walk_in_time: Optional[str] = None
    venue: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    contact_email: Optional[str] = None
    application_deadline: Optional[str] = None
    company_logo_b64: Optional[str] = None
    company_logo_mime: Optional[str] = None
    status: Optional[str] = None  # 'draft' | 'open' | 'closed'


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_common(payload: dict, is_draft: bool) -> dict:
    """Normalise + validate admin-job payload. On draft mode, only lightweight validation."""
    out = {}
    # Ints / positions
    if payload.get("open_positions") is not None:
        if not isinstance(payload["open_positions"], int) or payload["open_positions"] < 1:
            raise HTTPException(400, "Number of Open Positions must be a positive integer.")
        out["open_positions"] = payload["open_positions"]
    # Experience min/max consistency
    emin = payload.get("experience_min")
    emax = payload.get("experience_max")
    if emin is not None and emax is not None and emax < emin:
        raise HTTPException(400, "Maximum experience must be ≥ minimum experience.")
    if emin is not None:
        out["experience_min"] = int(emin)
    if emax is not None:
        out["experience_max"] = int(emax)
    # Contact number (only when non-empty, always validated when published)
    cn = (payload.get("contact_number") or "").strip()
    if cn:
        if not _MOBILE_RE.match(cn):
            raise HTTPException(400, "Contact Number must be a 10-digit Indian mobile (starting 6-9).")
        out["contact_number"] = cn
    # Contact email
    ce = (payload.get("contact_email") or "").strip()
    if ce:
        if not _EMAIL_RE.match(ce):
            raise HTTPException(400, "Contact Email is not a valid email address.")
        out["contact_email"] = ce
    # Dates future-only when publishing
    today = datetime.now(timezone.utc).date().isoformat()
    for f in ("walk_in_date", "application_deadline"):
        v = (payload.get(f) or "").strip()
        if v:
            if not _DATE_RE.match(v):
                raise HTTPException(400, f"{f.replace('_', ' ').title()} must be YYYY-MM-DD.")
            if not is_draft and v < today:
                raise HTTPException(400, f"{f.replace('_', ' ').title()} must be today or a future date.")
            out[f] = v
    return out


@router.post("/admin/jobs")
async def admin_create_job(body: AdminJobBody, u: dict = Depends(admin_only)):
    payload = body.model_dump()
    is_draft = (body.status or "").lower() == "draft"
    extras = _validate_common(payload, is_draft)
    # Fallback baseline experience_required for legacy filters
    exp_req = extras.get("experience_min") or 0
    category = payload.get("category") or ("experienced" if exp_req > 0 else "fresher")
    job = {
        "id": new_id(),
        "source": "admin",
        "employer_id": u["id"],  # admin user id — keeps existing PATCH/DELETE auth checks happy
        "employer_name": body.company.strip(),
        "posted_by_role": "admin",
        "posted_by_name": u.get("name") or "Admin",
        "title": body.title.strip(),
        "company": body.company.strip(),
        "description": body.description.strip(),
        "location": body.location.strip(),
        "skills_required": [s.strip() for s in body.skills_required if s.strip()],
        "employment_type": (body.employment_type or "Full-time").strip(),
        "salary_range": (body.salary_range or "").strip(),
        "salary_range_label": (body.salary_range or "").strip(),
        "industry_type": (body.industry_type or "").strip(),
        "category": category,
        "experience_required": int(exp_req or 0),
        "experience_min": extras.get("experience_min", exp_req or 0),
        "experience_max": extras.get("experience_max"),
        "open_positions": extras.get("open_positions", body.open_positions),
        "open_positions_label": str(extras.get("open_positions", body.open_positions)),
        # Walk-in / direct-only fields
        "walk_in_date": extras.get("walk_in_date", ""),
        "walk_in_time": (body.walk_in_time or "").strip(),
        "venue": (body.venue or "").strip(),
        "contact_person": (body.contact_person or "").strip(),
        "contact_number": extras.get("contact_number", ""),
        "contact_email": extras.get("contact_email", ""),
        "application_deadline": extras.get("application_deadline", ""),
        "company_logo_b64": (body.company_logo_b64 or "").strip(),
        "company_logo_mime": (body.company_logo_mime or "").strip().lower(),
        # Publish flow (admin jobs bypass approval)
        "status": "draft" if is_draft else "open",
        "verification_status": "verified",
        "verified_by": u["id"],
        "verified_at": now_iso(),
        "verification_note": "Admin-posted, auto-verified.",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.jobs.insert_one(job)
    await write_audit(u, "admin_job_create", "job", job["id"], before={}, after={"status": job["status"], "title": job["title"]})
    logger.info("Admin job %s created status=%s source=admin", job["id"], job["status"])
    return {k: v for k, v in job.items() if k != "_id"}


@router.get("/admin/jobs/mine")
async def admin_list_my_jobs(u: dict = Depends(admin_only)):
    """Return every job authored by the current admin (drafts + published + closed)."""
    jobs = await db.jobs.find({"source": "admin", "employer_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return jobs


@router.patch("/admin/jobs/{job_id}")
async def admin_edit_job(job_id: str, body: AdminJobPatchBody, u: dict = Depends(admin_only)):
    job = await db.jobs.find_one({"id": job_id, "source": "admin"})
    if not job:
        raise HTTPException(404, "Admin job not found.")
    payload = body.model_dump(exclude_unset=True)
    is_draft = (payload.get("status") or job.get("status") or "").lower() == "draft"
    extras = _validate_common(payload, is_draft)
    update = {"updated_at": now_iso()}
    # Straightforward fields
    for field in [
        "company", "title", "description", "location", "skills_required",
        "employment_type", "salary_range", "industry_type", "category",
        "walk_in_time", "venue", "contact_person",
        "company_logo_b64", "company_logo_mime", "status",
    ]:
        if field in payload and payload[field] is not None:
            v = payload[field]
            if isinstance(v, str):
                v = v.strip()
            update[field] = v
    # Validated / coerced fields
    for field in [
        "experience_min", "experience_max", "open_positions",
        "contact_number", "contact_email", "walk_in_date", "application_deadline",
    ]:
        if field in extras:
            update[field] = extras[field]
    # Keep denormalised fields in sync
    if "company" in update:
        update["employer_name"] = update["company"]
    if "open_positions" in update:
        update["open_positions_label"] = str(update["open_positions"])
    if update.get("status") == "open":
        update["verification_status"] = "verified"
    await db.jobs.update_one({"id": job_id}, {"$set": update})
    await write_audit(u, "admin_job_edit", "job", job_id, before={k: job.get(k) for k in update.keys() if k != "updated_at"}, after=update)
    return {"ok": True}


@router.post("/admin/jobs/{job_id}/publish")
async def admin_publish_job(job_id: str, u: dict = Depends(admin_only)):
    job = await db.jobs.find_one({"id": job_id, "source": "admin"})
    if not job:
        raise HTTPException(404, "Admin job not found.")
    if job.get("status") == "open":
        return {"ok": True, "already_published": True}
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "open", "verification_status": "verified", "updated_at": now_iso()}})
    await write_audit(u, "admin_job_publish", "job", job_id, before={"status": job.get("status")}, after={"status": "open"})
    return {"ok": True}
