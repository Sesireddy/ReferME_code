"""Admin endpoints — Phase D refactor.

All /admin/* endpoints extracted from server.py. URLs and behaviour preserved.
Shared helpers, models, and constants are imported from server.py which continues
to own the DB handle, auth deps, models, and cross-domain plumbing so existing
routers keep working unchanged.
"""
import io
import csv
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server import (
    db,
    admin_only,
    current_user,
    require_role,
    _credit_user,
    now_iso,
    new_id,
    push_notification,
    write_audit,
    user_public,
    expand_city,
    compute_pro_profile_completion,
    normalize_indian_mobile,
    ACTION_COST,
    HIRING_REWARD,
    REFERRAL_HIRED_REWARD,
    REDEMPTION_INR_PER_CREDIT,
    PAYOUT_MIN,
    JOB_POST_REWARD_MIN_APPS,
    MASTER_SKILLS,
    AUDIT_PURGE_DAYS,
    AdminStatusActionBody,
    AdminActionBody,
    AdminEditUserBody,
    AdminCreditAdjustBody,
    AdminCancelBookingBody,
    AdminVerifyJobBody,
    RedemptionPaidBody,
    RedemptionRejectBody,
    _serve,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/status-changes")
async def admin_status_changes(_: dict = Depends(admin_only)):
    items = await db.status_changes.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.post("/admin/status-changes/action")
async def admin_status_action(body: AdminStatusActionBody, _: dict = Depends(admin_only)):
    change = await db.status_changes.find_one({"id": body.change_id}, {"_id": 0})
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    if change["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")
    await db.status_changes.update_one(
        {"id": body.change_id},
        {"$set": {"status": body.action + "d" if body.action == "approve" else "rejected", "admin_note": body.note or "", "updated_at": now_iso()}},
    )
    if body.action == "approve":
        appdoc = await db.applications.find_one({"id": change["application_id"]}, {"_id": 0})
        if appdoc:
            new_hist = (appdoc.get("status_history") or []) + [{
                "status": change["to_status"],
                "at": now_iso(),
                "by": change["requested_by_id"],
                "note": change.get("note") or "",
            }]
            update_fields = {"status": change["to_status"], "status_history": new_hist}
            if change["to_status"] == "hired":
                update_fields["hired_at"] = now_iso()
            await db.applications.update_one({"id": appdoc["id"]}, {"$set": update_fields})
            # Hiring reward → goes to the JOB POSTER (employer/pro who owns the job)
            if change["to_status"] == "hired":
                job_owner_id = appdoc.get("employer_id")
                if job_owner_id:
                    await _credit_user(
                        job_owner_id,
                        HIRING_REWARD,
                        "hiring_reward",
                        {
                            "application_id": appdoc["id"],
                            "candidate_name": appdoc.get("student_name"),
                            "candidate_id": appdoc.get("student_id"),
                            "job_id": appdoc.get("job_id"),
                            "job_title": appdoc.get("job_title"),
                        },
                    )
                    await db.users.update_one({"id": job_owner_id}, {"$inc": {"successful_hires": 1}})
                    await push_notification(
                        job_owner_id,
                        f"Hiring bonus 💸 +{HIRING_REWARD} credits",
                        f"Verified hire of {appdoc.get('student_name')} for {appdoc.get('job_title')}.",
                        "success",
                    )
                # Referrer (separate person from job poster) keeps the smaller referral bonus
                if appdoc.get("referrer_pro_id") and appdoc.get("referrer_pro_id") != job_owner_id:
                    await _credit_user(appdoc["referrer_pro_id"], REFERRAL_HIRED_REWARD, "referral_hired", {"application_id": appdoc["id"]})
                    await db.users.update_one({"id": appdoc["referrer_pro_id"]}, {"$inc": {"successful_referrals": 1}})
                    await push_notification(appdoc["referrer_pro_id"], "Referral bonus 💸", f"+{REFERRAL_HIRED_REWARD} credits — candidate hired!", "success")
            await push_notification(
                appdoc["student_id"],
                "Status updated 📈" if change["to_status"] != "hired" else "You're hired! 🎉",
                f"Your application is now: {change['to_status'].replace('_', ' ').title()}",
                "success",
            )
    else:
        # Rejected — keep status as before
        await push_notification(change["requested_by_id"], "Status update rejected", body.note or "Please attach proof.", "error")
    return {"message": f"Change {body.action}d"}


@router.post("/admin/payouts/action")
async def admin_payout_action(body: AdminActionBody, _: dict = Depends(admin_only)):
    p = await db.payouts.find_one({"id": body.payout_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payout not found")
    if p["status"] != "requested":
        raise HTTPException(status_code=400, detail="Already processed")
    if body.action == "approve":
        await db.payouts.update_one(
            {"id": body.payout_id},
            {"$set": {"status": "approved", "admin_note": body.note, "updated_at": now_iso()}},
        )
        await push_notification(p["professional_id"], "Payout approved ✅", f"₹{p['amount_inr']} on the way.", "success")
    else:
        # refund credits
        await _credit_user(p["professional_id"], p["amount_inr"], "payout_refund", {"payout_id": p["id"]})
        await db.payouts.update_one(
            {"id": body.payout_id},
            {"$set": {"status": "rejected", "admin_note": body.note, "updated_at": now_iso()}},
        )
        await push_notification(p["professional_id"], "Payout rejected ❌", body.note or "Please contact support.", "error")
    return {"message": f"Payout {body.action}d"}


@router.get("/admin/users")
async def admin_users(_: dict = Depends(admin_only)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return [{**user_public(u), "account_status": u.get("account_status", "active")} for u in users]


@router.get("/admin/users/search")
async def admin_users_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None, description="Search ID/name/mobile/email/company/skill"),
    user_type: Optional[str] = Query(None),  # student | professional | employer
    location: Optional[str] = Query(None),
    profile_status: Optional[str] = Query(None),  # active | inactive | suspended
    mobile_verified: Optional[str] = Query(None),  # 'verified' | 'not_verified'
    email_verified: Optional[str] = Query(None),
    registration_range: Optional[str] = Query(None),  # today | last_7 | last_30 | custom
    registration_from: Optional[str] = Query(None),  # YYYY-MM-DD
    registration_to: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    f: dict = {}
    if user_type in ("student", "professional", "employer"):
        f["role"] = user_type
    if location:
        f["profile.current_location"] = {"$regex": re.escape(location), "$options": "i"}
    if profile_status == "suspended":
        f["account_status"] = "suspended"
    elif profile_status == "active":
        f["account_status"] = {"$ne": "suspended"}
        f["profile_complete"] = True
    elif profile_status == "inactive":
        f["account_status"] = {"$ne": "suspended"}
        f["profile_complete"] = False
    if email_verified == "verified":
        f["is_email_verified"] = True
    elif email_verified == "not_verified":
        f["is_email_verified"] = {"$ne": True}
    if mobile_verified == "verified":
        f["profile.phone_verified"] = True
    elif mobile_verified == "not_verified":
        f["profile.phone_verified"] = {"$ne": True}
    # Registration date filter
    now_dt = datetime.now(timezone.utc)
    if registration_range == "today":
        start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        f["created_at"] = {"$gte": start}
    elif registration_range == "last_7":
        f["created_at"] = {"$gte": (now_dt - timedelta(days=7)).isoformat().replace("+00:00", "Z")}
    elif registration_range == "last_30":
        f["created_at"] = {"$gte": (now_dt - timedelta(days=30)).isoformat().replace("+00:00", "Z")}
    elif registration_range == "custom":
        rng: dict = {}
        if registration_from:
            rng["$gte"] = registration_from
        if registration_to:
            rng["$lte"] = registration_to + "T23:59:59Z"
        if rng:
            f["created_at"] = rng
    # Free-text search across multiple fields
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [
            {"id": regex}, {"name": regex}, {"email": regex},
            {"profile.phone": regex},
            {"profile.company": regex}, {"profile.company_name": regex},
            {"profile.skills": regex},
            {"profile.current_location": regex},
        ]
    users = await db.users.find(f, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(limit)
    return [{**user_public(u), "account_status": u.get("account_status", "active")} for u in users]


@router.post("/admin/users/{user_id}/suspend")
async def admin_suspend(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.update_one({"id": user_id}, {"$set": {"account_status": "suspended"}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Suspended"}


@router.post("/admin/users/{user_id}/activate")
async def admin_activate(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.update_one({"id": user_id}, {"$set": {"account_status": "active"}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Activated"}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _: dict = Depends(admin_only)):
    res = await db.users.delete_one({"id": user_id, "role": {"$ne": "admin"}})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="User not found or admin cannot be deleted")
    return {"message": "Deleted"}


@router.get("/admin/jobs")
async def admin_all_jobs(_: dict = Depends(admin_only)):
    return await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.delete("/admin/jobs/{job_id}")
async def admin_delete_job(job_id: str, _: dict = Depends(admin_only)):
    res = await db.jobs.delete_one({"id": job_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job removed"}


@router.get("/admin/interviews")
async def admin_interviews(_: dict = Depends(admin_only)):
    return await db.interview_slots.find({}, {"_id": 0}).sort("start_at", -1).to_list(500)


@router.delete("/admin/interviews/{slot_id}")
async def admin_cancel_slot(slot_id: str, _: dict = Depends(admin_only)):
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    await db.interview_slots.update_one({"id": slot_id}, {"$set": {"status": "cancelled"}})
    if slot.get("student_id"):
        # Refund the exact amount the student was charged for this booking
        # (persisted on the slot at booking time — falls back to legacy ACTION_COST).
        refund_amount = int(slot.get("credits_charged") or ACTION_COST)
        await _credit_user(slot["student_id"], refund_amount, "interview_cancel_refund", {"slot_id": slot_id, "amount": refund_amount})
        await push_notification(slot["student_id"], "Interview cancelled", f"{refund_amount} credits refunded.", "warning")
    return {"message": "Slot cancelled"}


@router.post("/admin/wallet/refund")
async def admin_refund(user_id: str = Query(...), amount: int = Query(...), reason: str = Query("admin_refund"), _: dict = Depends(admin_only)):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    new_balance = await _credit_user(user_id, amount, reason, {"by": "admin"})
    await push_notification(user_id, "Credit adjustment", f"+{amount} credits applied by admin.", "info")
    return {"credits": new_balance}


@router.get("/admin/stats")
async def admin_stats(_: dict = Depends(admin_only)):
    deposits = await db.deposit_orders.find({"status": "paid"}, {"_id": 0, "amount_inr": 1, "created_at": 1}).to_list(20000)
    revenue = sum(int(d.get("amount_inr", 0)) for d in deposits)
    hires = await db.applications.count_documents({"status": "hired"})
    referrals_done = await db.applications.count_documents({"referrer_pro_id": {"$ne": None}})
    return {
        "total_users": await db.users.count_documents({}),
        "students": await db.users.count_documents({"role": "student"}),
        "professionals": await db.users.count_documents({"role": "professional"}),
        "employers": await db.users.count_documents({"role": "employer"}),
        "active_students": await db.users.count_documents({"role": "student", "account_status": {"$ne": "suspended"}}),
        "active_professionals": await db.users.count_documents({"role": "professional", "account_status": {"$ne": "suspended"}}),
        "jobs": await db.jobs.count_documents({}),
        "jobs_open": await db.jobs.count_documents({"status": "open"}),
        "applications": await db.applications.count_documents({}),
        "referrals_completed": referrals_done,
        "interviews": await db.interview_slots.count_documents({"status": "completed"}),
        "hires": hires,
        "revenue_inr": revenue,
        "payouts_pending": await db.payouts.count_documents({"status": "requested"}),
        "disputes_open": await db.disputes.count_documents({"status": "open"}),
        "status_changes_pending": await db.status_changes.count_documents({"status": "pending"}),
    }


@router.get("/admin/stats/overview")
async def admin_stats_overview(_: dict = Depends(admin_only)):
    """Per-module KPI groups for the admin dashboard — calculated dynamically from live data."""
    now_dt = datetime.now(timezone.utc)
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    month_start_dt = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = month_start_dt.isoformat().replace("+00:00", "Z")

    # USERS
    users = {
        "total": await db.users.count_documents({}),
        "students": await db.users.count_documents({"role": "student"}),
        "professionals": await db.users.count_documents({"role": "professional"}),
        "employers": await db.users.count_documents({"role": "employer"}),
        "active": await db.users.count_documents({"account_status": {"$ne": "suspended"}}),
        "new_today": await db.users.count_documents({"created_at": {"$gte": today_start}}),
    }
    # JOBS
    jobs = {
        "total": await db.jobs.count_documents({}),
        "active": await db.jobs.count_documents({"status": "open"}),
        "closed": await db.jobs.count_documents({"status": "closed"}),
        "posted_today": await db.jobs.count_documents({"created_at": {"$gte": today_start}}),
    }
    # APPLICATIONS
    app_status_counts: dict[str, int] = {}
    for r in await db.applications.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(50):
        app_status_counts[r["_id"]] = r["n"]
    apps = {
        "total": await db.applications.count_documents({}),
        "applied": app_status_counts.get("applied", 0),
        "shortlisted": app_status_counts.get("shortlisted", 0),
        "referred": app_status_counts.get("referred", 0),
        "interview_scheduled": app_status_counts.get("interview_scheduled", 0) + app_status_counts.get("awaiting_interview", 0),
        "hired": app_status_counts.get("hired", 0),
        "rejected": app_status_counts.get("rejected", 0),
    }
    # INTERVIEWS
    interview_status_counts: dict[str, int] = {}
    for r in await db.interview_slots.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(20):
        interview_status_counts[r["_id"]] = r["n"]
    interviews = {
        "slots_total": await db.interview_slots.count_documents({}),
        "available": interview_status_counts.get("available", 0),
        "booked": interview_status_counts.get("booked", 0),
        "completed": interview_status_counts.get("completed", 0),
        "cancelled": interview_status_counts.get("cancelled", 0),
    }
    # CREDITS — sum txn amounts by reason bucket
    credit_buckets = {"purchased": 0, "used": 0, "earned": 0, "rewarded": 0}
    REWARD_REASONS = {"interview_pro_reward", "job_post_reward", "hiring_reward", "referral_hired_reward", "mock_interview_reward"}
    USED_REASONS = {"job_application", "interview_booking"}
    # Wallet deposit reasons written by different code paths — accept all of them.
    PURCHASE_REASONS = {"wallet_deposit", "wallet_deposit_confirm", "credit_purchase", "deposit", "signup_bonus", "first_deposit_bonus"}
    # Transactions are stored with the signed amount on the field name `delta` — historical
    # readers referenced `amount` (which does not exist) and always saw 0. Read both for safety.
    async for t in db.transactions.find({}, {"_id": 0, "delta": 1, "amount": 1, "reason": 1}):
        amt = int(t.get("delta", t.get("amount", 0)) or 0)
        reason = t.get("reason", "")
        if amt > 0:
            if reason in PURCHASE_REASONS:
                credit_buckets["purchased"] += amt
            else:
                credit_buckets["earned"] += amt
                if reason in REWARD_REASONS:
                    credit_buckets["rewarded"] += amt
        else:
            if reason in USED_REASONS:
                credit_buckets["used"] += -amt
    credits = credit_buckets
    # REVENUE
    today_rev = 0
    month_rev = 0
    total_rev = 0
    async for d in db.deposit_orders.find({"status": "paid"}, {"_id": 0, "amount_inr": 1, "created_at": 1}):
        amt = int(d.get("amount_inr", 0))
        total_rev += amt
        c = d.get("created_at", "")
        if c >= today_start:
            today_rev += amt
        if c >= month_start:
            month_rev += amt
    revenue = {"total_inr": total_rev, "today_inr": today_rev, "monthly_inr": month_rev}
    return {"users": users, "jobs": jobs, "applications": apps,
            "interviews": interviews, "credits": credits, "revenue": revenue}


@router.get("/admin/jobs/search")
async def admin_jobs_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None, description="Global search across id/title/company"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    salary_range: Optional[str] = Query(None),
    posted_date: Optional[str] = Query(None, description="YYYY-MM-DD; jobs posted on this date"),
    job_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(200, le=1000),
):
    f: dict = {}
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"id": regex}, {"title": regex}, {"company": regex}]
    if company:
        f["company"] = {"$regex": re.escape(company), "$options": "i"}
    if location:
        f["location"] = {"$regex": re.escape(location), "$options": "i"}
    if category:
        f["category"] = category
    if industry:
        f["industry_type"] = {"$regex": re.escape(industry), "$options": "i"}
    if salary_range:
        f["salary_range_label"] = salary_range
    if job_status:
        f["status"] = job_status
    if posted_date:
        f["created_at"] = {"$gte": posted_date, "$lt": posted_date + "T23:59:59Z"}
    jobs = await db.jobs.find(f, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # annotate counts
    if jobs:
        ids = [j["id"] for j in jobs]
        agg = await db.applications.aggregate([
            {"$match": {"job_id": {"$in": ids}}},
            {"$group": {"_id": {"job": "$job_id", "status": "$status"}, "n": {"$sum": 1}}},
        ]).to_list(5000)
        amap: dict[str, int] = {}
        smap: dict[str, int] = {}
        for r in agg:
            jid = r["_id"]["job"]
            st = r["_id"]["status"]
            if st == "withdrawn":
                continue
            amap[jid] = amap.get(jid, 0) + r["n"]
            if st in ("shortlisted", "interview_scheduled", "awaiting_interview", "hired"):
                smap[jid] = smap.get(jid, 0) + r["n"]
        for j in jobs:
            j["applied_count"] = amap.get(j["id"], 0)
            j["shortlisted_count"] = smap.get(j["id"], 0)
    return jobs


@router.get("/admin/interviews/search")
async def admin_interviews_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None),
    candidate: Optional[str] = Query(None),
    pro: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    date: Optional[str] = Query(None),  # YYYY-MM-DD start_at on that day
    slot_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(300, le=2000),
):
    f: dict = {}
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"id": regex}, {"student_name": regex}, {"pro_name": regex}, {"meeting_url": regex}]
    if candidate:
        f["student_name"] = {"$regex": re.escape(candidate), "$options": "i"}
    if pro:
        f["pro_name"] = {"$regex": re.escape(pro), "$options": "i"}
    if skill:
        f["skill_set"] = {"$regex": re.escape(skill), "$options": "i"}
    if slot_status:
        f["status"] = slot_status
    if date:
        f["start_at"] = {"$gte": date, "$lt": date + "T23:59:59Z"}
    slots = await db.interview_slots.find(f, {"_id": 0}).sort("start_at", -1).to_list(limit)
    return slots


@router.get("/admin/transactions/search")
async def admin_transactions_search(
    _: dict = Depends(admin_only),
    q: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),  # student | professional | employer
    type: Optional[str] = Query(None, description="purchase | application | interview_reward | job_post_reward | hiring_reward | manual"),
    date_from: Optional[str] = Query(None),  # YYYY-MM-DD inclusive
    date_to: Optional[str] = Query(None),
    limit: int = Query(500, le=5000),
):
    txn_filter: dict = {}
    # Map UI transaction type → internal `reason` set
    type_map = {
        "purchase": {"wallet_deposit", "wallet_deposit_confirm", "credit_purchase"},
        "application": {"job_application"},
        "interview_reward": {"interview_pro_reward"},
        "job_post_reward": {"job_post_reward"},
        "hiring_reward": {"hiring_reward", "referral_hired_reward"},
        "manual": {"admin_refund", "admin_adjustment"},
    }
    if type and type in type_map:
        txn_filter["reason"] = {"$in": list(type_map[type])}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59Z"
        txn_filter["created_at"] = rng
    transactions = await db.transactions.find(txn_filter, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # Hydrate user details (name / email / role)
    user_ids = list({t.get("user_id") for t in transactions if t.get("user_id")})
    users_lookup: dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}):
            users_lookup[u["id"]] = u
    out = []
    for t in transactions:
        u = users_lookup.get(t.get("user_id"), {})
        if user_type and u.get("role") != user_type:
            continue
        if q:
            target = " ".join([t.get("id", ""), u.get("name", ""), u.get("email", ""), str(t.get("reason", ""))]).lower()
            if q.lower() not in target:
                continue
        # Transactions store the signed credit amount on the `delta` field (historical readers
        # incorrectly referenced `amount` and always saw 0). Read both for safety.
        amt = int(t.get("delta", t.get("amount", 0)) or 0)
        out.append({
            "id": t.get("id"),
            "user_id": t.get("user_id"),
            "user_name": u.get("name") or (u.get("email", "").split("@")[0] if u.get("email") else "—"),
            "user_email": u.get("email"),
            "user_type": u.get("role"),
            "credits_added": amt if amt > 0 else 0,
            "credits_deducted": -amt if amt < 0 else 0,
            "amount": amt,
            "reason": t.get("reason"),
            "reference": t.get("meta", {}),
            "created_at": t.get("created_at"),
            "status": t.get("status", "completed"),
        })
    return out


@router.post("/admin/disputes/{dispute_id}/resolve")
async def resolve_dispute(dispute_id: str, _: dict = Depends(admin_only)):
    res = await db.disputes.update_one({"id": dispute_id}, {"$set": {"status": "resolved", "updated_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return {"message": "Resolved"}


@router.get("/admin/interview-bookings")
async def admin_list_interview_bookings(u: dict = Depends(require_role(["admin"]))):
    """List every Mock Interview booking with full Pro & Student details, slot info,
    meeting link, status, booking timestamp and per-recipient email delivery status."""
    bookings = await db.interview_bookings.find({}, {"_id": 0}).sort("booked_at", -1).to_list(2000)
    # Hydrate latest slot status (in case it was cancelled/completed after booking)
    slot_ids = [b["slot_id"] for b in bookings if b.get("slot_id")]
    slot_map = {}
    if slot_ids:
        slots = await db.interview_slots.find({"id": {"$in": slot_ids}}, {"_id": 0, "id": 1, "status": 1}).to_list(2000)
        slot_map = {s["id"]: s.get("status") for s in slots}
    for b in bookings:
        b["current_slot_status"] = slot_map.get(b.get("slot_id"), "deleted")
    return bookings


@router.get("/admin/redemption-requests")
async def admin_list_redemptions(
    status_f: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = None,
    limit: int = 100,
    _: dict = Depends(admin_only),
):
    flt: dict[str, Any] = {}
    if status_f and status_f.lower() != "all":
        flt["status"] = status_f.lower()
    if q:
        rgx = re.compile(re.escape(q.strip()), re.IGNORECASE)
        flt["$or"] = [
            {"pro_name": rgx},
            {"pro_email": rgx},
            {"id": rgx},
            {"upi_id": rgx},
        ]
    items = await db.redemption_requests.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 500))
    counts = {}
    for s in ("pending", "approved", "paid", "rejected"):
        counts[s] = await db.redemption_requests.count_documents({"status": s})
    return {"items": items, "counts": counts}


@router.post("/admin/redemption-requests/{req_id}/approve")
async def admin_approve_redemption(req_id: str, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve a {r['status']} request")
    now = now_iso()
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "approved", "approved_at": now, "updated_at": now}},
    )
    await push_notification(
        r["pro_id"],
        "Redemption approved ✅",
        f"Your redemption of {r['credits_requested']} credits is approved. Payment in progress.",
        "success",
    )
    return {"ok": True, "status": "approved"}


@router.post("/admin/redemption-requests/{req_id}/mark-paid")
async def admin_mark_redemption_paid(req_id: str, body: RedemptionPaidBody, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] not in ("approved", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot mark a {r['status']} request as paid")
    now = now_iso()
    pay_date = body.payment_date or now
    # Burn the locked credits (payment was made out of platform)
    await db.users.update_one(
        {"id": r["pro_id"]},
        {"$inc": {"locked_credits": -r["credits_requested"]}},
    )
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "paid",
            "payment_ref": body.payment_ref.strip(),
            "payment_date": pay_date,
            "remarks": (body.remarks or "").strip(),
            "paid_at": now,
            "updated_at": now,
        }},
    )
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": r["pro_id"],
        "delta": 0,
        "reason": "redemption_paid",
        "meta": {
            "request_id": req_id,
            "credits_redeemed": r["credits_requested"],
            "amount_inr": r["amount_inr"],
            "payment_ref": body.payment_ref.strip(),
            "payment_date": pay_date,
        },
        "created_at": now,
    })
    await push_notification(
        r["pro_id"],
        "Redemption paid 💸",
        f"Your redemption request has been processed and ₹{r['amount_inr']:.2f} has been transferred to your provided account/UPI. Ref: {body.payment_ref.strip()}.",
        "success",
    )
    return {"ok": True, "status": "paid"}


@router.post("/admin/redemption-requests/{req_id}/reject")
async def admin_reject_redemption(req_id: str, body: RedemptionRejectBody, _: dict = Depends(admin_only)):
    r = await db.redemption_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] in ("paid", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot reject a {r['status']} request")
    now = now_iso()
    # Restore locked credits back to available
    await db.users.update_one(
        {"id": r["pro_id"]},
        {"$inc": {"locked_credits": -r["credits_requested"], "credits": r["credits_requested"]}},
    )
    await db.redemption_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "rejected",
            "rejection_reason": body.reason.strip(),
            "rejected_at": now,
            "updated_at": now,
        }},
    )
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": r["pro_id"],
        "delta": r["credits_requested"],
        "reason": "redemption_refunded",
        "meta": {"request_id": req_id, "rejection_reason": body.reason.strip()},
        "created_at": now,
    })
    await push_notification(
        r["pro_id"],
        "Redemption rejected ⚠️",
        f"Your redemption request was rejected: {body.reason.strip()}. {r['credits_requested']} credits returned to your balance.",
        "warning",
    )
    return {"ok": True, "status": "rejected"}


@router.patch("/admin/users/{user_id}")
async def admin_edit_user(user_id: str, body: AdminEditUserBody, admin: dict = Depends(admin_only)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    allowed_roles = {"student", "professional", "employer", "admin"}
    allowed_status = {"active", "suspended"}

    update: dict[str, Any] = {}
    if body.name is not None:
        update["name"] = body.name.strip()
    if body.role is not None:
        if body.role not in allowed_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {sorted(allowed_roles)}")
        update["role"] = body.role
    if body.account_status is not None:
        if body.account_status not in allowed_status:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(allowed_status)}")
        update["account_status"] = body.account_status

    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided.")

    before_snap = {k: user.get(k) for k in update.keys()}
    await db.users.update_one({"id": user_id}, {"$set": update})
    after_snap = update
    await write_audit(
        admin, "user.edit", "user", user_id,
        before=before_snap, after=after_snap, reason=body.reason or "",
        extra={"target_email": user.get("email", "")},
    )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"ok": True, "user": updated}


@router.post("/admin/users/{user_id}/credits/adjust")
async def admin_adjust_credits(user_id: str, body: AdminCreditAdjustBody, admin: dict = Depends(admin_only)):
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="Delta must be non-zero.")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    before_credits = user.get("credits", 0)

    # If deducting, ensure not going below zero
    if body.delta < 0 and before_credits + body.delta < 0:
        raise HTTPException(status_code=400, detail=f"Cannot deduct {-body.delta}. User has only {before_credits} credits.")

    now = now_iso()
    await db.users.update_one({"id": user_id}, {"$inc": {"credits": body.delta}})
    # Ledger entry
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "delta": body.delta,
        "reason": "admin_adjustment",
        "meta": {
            "label": f"Admin Adjustment ({'+' if body.delta > 0 else ''}{body.delta})",
            "admin_id": admin.get("id", ""),
            "admin_email": admin.get("email", ""),
            "note": body.reason,
        },
        "created_at": now,
    })
    after_credits = before_credits + body.delta
    await write_audit(
        admin, "user.credits.adjust", "credit_adjustment", user_id,
        before={"credits": before_credits},
        after={"credits": after_credits},
        reason=body.reason,
        extra={"target_email": user.get("email", ""), "delta": body.delta},
    )
    await push_notification(
        user_id,
        f"Credits {'added' if body.delta > 0 else 'adjusted'}",
        f"{abs(body.delta)} credits {'added to' if body.delta > 0 else 'deducted from'} your wallet by admin. New balance: {after_credits}.",
        "info",
    )
    return {"ok": True, "credits": after_credits, "delta": body.delta}


@router.post("/admin/interviews/bookings/{booking_id}/cancel")
async def admin_cancel_booking(booking_id: str, body: AdminCancelBookingBody, admin: dict = Depends(admin_only)):
    bk = await db.interview_bookings.find_one({"id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    if bk.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Booking already cancelled.")
    now = now_iso()

    # Release the slot back to 'available' so other students can book it
    if bk.get("slot_id"):
        await db.interview_slots.update_one(
            {"id": bk["slot_id"]},
            {"$set": {"status": "available"}, "$unset": {"student_id": "", "student_name": "", "student_email": "", "booked_at": ""}},
        )

    # Mark booking cancelled
    await db.interview_bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "cancelled", "cancelled_at": now, "cancel_reason": body.reason, "cancelled_by": admin.get("email", "")}},
    )

    # Refund credits to student
    refund_amount = 0
    if body.refund and bk.get("student_id"):
        refund_amount = int(bk.get("credits_charged") or ACTION_COST)
        await db.users.update_one({"id": bk["student_id"]}, {"$inc": {"credits": refund_amount}})
        await db.transactions.insert_one({
            "id": new_id(),
            "user_id": bk["student_id"],
            "delta": refund_amount,
            "reason": "interview_admin_refund",
            "meta": {
                "label": "Mock Interview Refund (Admin Cancelled)",
                "booking_id": booking_id,
                "admin_id": admin.get("id", ""),
                "admin_email": admin.get("email", ""),
                "note": body.reason,
            },
            "created_at": now,
        })
        await push_notification(
            bk["student_id"],
            "Mock interview cancelled",
            f"Your booking on {bk.get('start_at','')} has been cancelled by admin. {refund_amount} credits have been refunded. Reason: {body.reason}",
            "warning",
        )
    # Notify pro
    if bk.get("pro_id"):
        await push_notification(
            bk["pro_id"],
            "Mock interview cancelled by admin",
            f"The booking with {bk.get('student_name','student')} on {bk.get('start_at','')} has been cancelled. Reason: {body.reason}",
            "info",
        )

    await write_audit(
        admin, "interview_booking.cancel", "interview_booking", booking_id,
        before={"status": bk.get("status", ""), "student_id": bk.get("student_id", "")},
        after={"status": "cancelled", "refund": refund_amount},
        reason=body.reason,
        extra={
            "student_email": bk.get("student_email", ""),
            "pro_email": bk.get("pro_email", ""),
            "slot_id": bk.get("slot_id", ""),
            "start_at": bk.get("start_at", ""),
        },
    )
    return {"ok": True, "status": "cancelled", "refund": refund_amount}


@router.get("/admin/audit-logs")
async def admin_list_audit_logs(
    action: Optional[str] = None,
    entity: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    _: dict = Depends(admin_only),
):
    flt: dict[str, Any] = {}
    if action:
        flt["action"] = action
    if entity:
        flt["entity_type"] = entity
    if q:
        rgx = re.compile(re.escape(q.strip()), re.IGNORECASE)
        flt["$or"] = [
            {"actor_email": rgx},
            {"actor_name": rgx},
            {"entity_id": rgx},
            {"reason": rgx},
            {"extra.target_email": rgx},
            {"extra.job_title": rgx},
        ]
    items = await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    return {
        "items": items,
        "retention_days_for_jobs_and_interviews": AUDIT_PURGE_DAYS,
    }


@router.post("/admin/interviews/slots/{slot_id}/cancel-booking")
async def admin_cancel_slot_booking(slot_id: str, body: AdminCancelBookingBody, admin: dict = Depends(admin_only)):
    """Convenience wrapper: find the active booking on this slot and cancel it."""
    bk = await db.interview_bookings.find_one({"slot_id": slot_id, "status": {"$ne": "cancelled"}}, {"_id": 0})
    if not bk:
        raise HTTPException(status_code=404, detail="No active booking found for this slot.")
    return await admin_cancel_booking(bk["id"], body, admin)


@router.get("/admin/export/users")
async def admin_export_users(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(10000)
    header = ["ID", "Name", "Email", "Role", "Status", "Credits", "Locked Credits", "Email Verified", "Mobile", "Mobile Verified", "Created At"]
    rows = [
        [
            u.get("id"), u.get("name"), u.get("email"), u.get("role"),
            u.get("account_status", "active"),
            u.get("credits", 0), u.get("locked_credits", 0),
            "Yes" if u.get("is_email_verified") else "No",
            (u.get("profile") or {}).get("phone", ""),
            "Yes" if (u.get("profile") or {}).get("phone_verified") else "No",
            u.get("created_at", ""),
        ]
        for u in users
    ]
    return _serve(rows, header, f"referme_users_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Users Export", fmt)


@router.get("/admin/export/jobs")
async def admin_export_jobs(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    jobs = await db.jobs.find({}, {"_id": 0}).to_list(10000)
    header = ["ID", "Title", "Company", "Location", "Industry", "Salary Range", "Status", "Posted By Email", "Created At"]
    rows = [
        [
            j.get("id"), j.get("title"), j.get("company_name", ""),
            j.get("location"), j.get("industry_type", ""), j.get("salary_range", ""),
            j.get("status", "active"), j.get("poster_email", ""),
            j.get("created_at", ""),
        ]
        for j in jobs
    ]
    return _serve(rows, header, f"referme_jobs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Jobs Export", fmt)


@router.get("/admin/export/interviews")
async def admin_export_interviews(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    slots = await db.interview_slots.find({}, {"_id": 0}).to_list(10000)
    header = ["Slot ID", "Pro Name", "Pro Email", "Student Name", "Student Email", "Skills", "Category", "Start At", "End At", "Status", "Meeting URL"]
    rows = [
        [
            s.get("id"), s.get("pro_name"), s.get("pro_email", ""),
            s.get("student_name", ""), s.get("student_email", ""),
            ", ".join(s.get("skill_set", []) or []),
            s.get("category", ""), s.get("start_at", ""), s.get("end_at", ""),
            s.get("status", ""), s.get("meeting_url", ""),
        ]
        for s in slots
    ]
    return _serve(rows, header, f"referme_interviews_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Interview Slots Export", fmt)


@router.get("/admin/export/transactions")
async def admin_export_transactions(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    txs = await db.transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(20000)
    # Resolve user emails for richer output
    user_ids = list({t.get("user_id") for t in txs if t.get("user_id")})
    user_map: dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}):
            user_map[u["id"]] = u
    header = ["Tx ID", "User Email", "User Role", "Delta", "Reason", "Label", "Created At"]
    rows = [
        [
            t.get("id"),
            (user_map.get(t.get("user_id", "")) or {}).get("email", ""),
            (user_map.get(t.get("user_id", "")) or {}).get("role", ""),
            t.get("delta", 0),
            t.get("reason", ""),
            (t.get("meta") or {}).get("label", ""),
            t.get("created_at", ""),
        ]
        for t in txs
    ]
    return _serve(rows, header, f"referme_credits_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Credit Transactions Export", fmt)


@router.get("/admin/export/redemptions")
async def admin_export_redemptions(fmt: str = Query("csv"), _: dict = Depends(admin_only)):
    items = await db.redemption_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    header = ["Request ID", "Pro Name", "Pro Email", "Credits Requested", "Amount INR", "UPI ID", "Bank Account", "IFSC", "Status", "Payment Ref", "Payment Date", "Rejection Reason", "Created At"]
    rows = [
        [
            r.get("id"), r.get("pro_name"), r.get("pro_email"),
            r.get("credits_requested", 0), f"{r.get('amount_inr', 0):.2f}",
            r.get("upi_id", ""), r.get("bank_account", ""), r.get("ifsc", ""),
            r.get("status", ""), r.get("payment_ref", ""), r.get("payment_date", ""),
            r.get("rejection_reason", ""), r.get("created_at", ""),
        ]
        for r in items
    ]
    return _serve(rows, header, f"referme_redemptions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}", "Redemption Requests Export", fmt)


@router.post("/admin/jobs/{job_id}/verify")
async def admin_verify_job(job_id: str, body: AdminVerifyJobBody, admin: dict = Depends(admin_only)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if body.decision == "rejected" and not (body.note or "").strip():
        raise HTTPException(status_code=400, detail="Rejection reason is required.")
    now = now_iso()
    before = {"verification_status": job.get("verification_status", "pending")}
    after = {
        "verification_status": body.decision,
        "verified_by": admin.get("email", ""),
        "verified_at": now,
        "verification_note": (body.note or "").strip(),
        "updated_at": now,
    }
    await db.jobs.update_one({"id": job_id}, {"$set": after})
    await write_audit(
        admin, "job.verify", "job", job_id,
        before=before, after={"verification_status": body.decision},
        reason=body.note or "",
        extra={"job_title": job.get("title", "")},
    )
    # Notify the poster
    if job.get("employer_id"):
        if body.decision == "verified":
            await push_notification(
                job["employer_id"],
                "Job verified ✅",
                f"Your job posting '{job.get('title','')}' has been verified and is now public.",
                "success",
            )
        else:
            await push_notification(
                job["employer_id"],
                "Job verification rejected",
                f"Your job posting '{job.get('title','')}' was rejected. Reason: {body.note or 'not specified'}",
                "warning",
            )
    return {"ok": True, "verification_status": body.decision}


