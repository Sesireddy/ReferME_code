"""Leaderboard endpoints — TPS (students) + WPS (professionals).

Refactored out of server.py in Phase A. URLs and response shapes unchanged.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query

from server import (
    db,
    current_user,
    require_role,
    compute_tps,
    compute_wps,
    MASTER_SKILLS,
)


router = APIRouter()


@router.get("/leaderboard/students/options")
async def leaderboard_options(u: dict = Depends(current_user)):
    """Return dynamic dropdown options for the leaderboard skill / location filters."""
    skill_set: set[str] = set()
    async for s in db.users.find({"role": "student"}, {"_id": 0, "profile.skills": 1}):
        for sk in (s.get("profile", {}) or {}).get("skills", []) or []:
            sk = (sk or "").strip()
            if sk:
                skill_set.add(sk)
    async for j in db.jobs.find({}, {"_id": 0, "required_skills": 1, "skills": 1}):
        for key in ("required_skills", "skills"):
            for sk in (j.get(key) or []):
                sk = (sk or "").strip()
                if sk:
                    skill_set.add(sk)
    skill_set.update(MASTER_SKILLS)

    canon: dict[str, str] = {}
    for sk in skill_set:
        key = sk.lower()
        if key not in canon or len(sk) > len(canon[key]):
            canon[key] = sk
    skills_sorted = sorted(canon.values(), key=lambda x: x.lower())

    loc_set: set[str] = set()
    async for s in db.users.find({"role": "student"}, {"_id": 0, "profile.current_location": 1}):
        loc = ((s.get("profile") or {}).get("current_location") or "").strip()
        if loc:
            loc_set.add(loc)
    locations_sorted = sorted(loc_set, key=lambda x: x.lower())

    return {"skills": skills_sorted, "locations": locations_sorted}


@router.get("/leaderboard/students")
async def leaderboard_students(
    u: dict = Depends(current_user),
    category: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    """LeaderBoard — ranks Students by Talent Potential Score (TPS).

    NOTE: `to_list(None)` (uncapped) is used so `total` reflects the true count
    of matching Students regardless of DB size. Previously capped at 5000, which
    silently showed 5000 as the total even when the real count was higher.
    """
    students = await db.users.find({"role": "student"}, {"_id": 0, "password_hash": 0}).to_list(None)
    out: list[dict] = []
    for s in students:
        sid = s["id"]
        profile = s.get("profile", {}) or {}
        skills = profile.get("skills", []) or []
        cat = profile.get("preferred_role")
        loc = profile.get("current_location")
        score_val = int(profile.get("resume_score") or 0)
        attended = int(s.get("interviews_attended", 0) or 0)
        avg_rating = float(s.get("student_rating") or 0)

        if category and cat != category:
            continue
        if skill and not any(skill.lower() == (sk or "").lower() for sk in skills):
            continue
        if location and location.lower() != (loc or "").lower():
            continue

        tps = profile.get("tps")
        if tps is None:
            tps = compute_tps(s)

        primary_skill = (skills[0] if skills else "") or "—"
        out.append({
            "id": sid,
            "name": s.get("name") or s["email"].split("@")[0],
            "category": cat or "—",
            "skills": skills,
            "skill_set": primary_skill,
            "current_location": loc or "—",
            "tps": round(float(tps), 2),
            "resume_score": score_val,
            "interviews_attended": attended,
            "avg_rating": round(avg_rating, 2),
            "rating": avg_rating,
            "composite_score": round(float(tps), 2),
            "is_me": sid == u["id"],
        })
    out.sort(key=lambda x: (-x["tps"], -x["resume_score"], -x["avg_rating"], -x["interviews_attended"]))
    for i, e in enumerate(out):
        e["rank"] = i + 1
    total = len(out)
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": total, "page": page, "page_size": page_size, "items": out[start:end]}


@router.get("/leaderboard/professionals")
async def leaderboard_pros(u: dict = Depends(current_user)):
    """Working Professionals ranked by WPS."""
    pros = await db.users.find({"role": "professional"}, {"_id": 0, "password_hash": 0}).to_list(None)
    pro_ids = [p["id"] for p in pros]
    counts = {}
    if pro_ids:
        async for row in db.jobs.aggregate([
            {"$match": {"posted_by": {"$in": pro_ids}}},
            {"$group": {"_id": "$posted_by", "n": {"$sum": 1}}},
        ]):
            counts[row["_id"]] = row.get("n", 0)
    enriched = []
    for p in pros:
        ints = int(p.get("interviews_conducted", 0) or 0)
        jobs = int(counts.get(p["id"], 0))
        wps = compute_wps(ints, jobs)
        enriched.append({
            "id": p["id"],
            "name": p.get("name") or p["email"].split("@")[0],
            "interviews_conducted": ints,
            "jobs_posted": jobs,
            "referrals_made": int(p.get("referrals_made", 0) or 0),
            "successful_referrals": int(p.get("successful_referrals", 0) or 0),
            "rating": float(p.get("rating") or 0),
            "ratings_count": int(p.get("ratings_count") or 0),
            "wps": wps,
            "is_me": p["id"] == u["id"],
        })
    enriched.sort(key=lambda x: (-x["wps"], -x["interviews_conducted"], -x["jobs_posted"]))
    for i, e in enumerate(enriched):
        e["rank"] = i + 1
        e["score"] = e["wps"]
    return enriched[:200]


@router.get("/leaderboard/professional/me/stats")
async def my_pro_stats(u: dict = Depends(require_role(["professional"]))):
    """Personal WPS + rank summary for the Working Professional menu screen."""
    board = await leaderboard_pros(u)
    me = next((b for b in board if b["is_me"]), None)
    if not me:
        ints = int(u.get("interviews_conducted", 0) or 0)
        jobs = int(await db.jobs.count_documents({"posted_by": u["id"]}))
        wps = compute_wps(ints, jobs)
        me = {
            "rank": None,
            "interviews_conducted": ints,
            "jobs_posted": jobs,
            "wps": wps,
            "rating": float(u.get("rating") or 0),
            "ratings_count": int(u.get("ratings_count") or 0),
            "successful_referrals": int(u.get("successful_referrals") or 0),
        }
    return {
        "rank": me.get("rank"),
        "interviews_conducted": me["interviews_conducted"],
        "jobs_posted": me["jobs_posted"],
        "wps": me["wps"],
        "rating": me.get("rating"),
        "ratings_count": me.get("ratings_count"),
        "successful_referrals": me.get("successful_referrals"),
        "total_pros": len(board),
    }
