"""Referral Program endpoints (refactored out of server.py — Phase A).

All endpoints retain their original URLs (`/api/refer/...`) and behaviour.
Shared helpers (`db`, `current_user`, `REFERRAL_REWARD`, etc.) are imported
from `server.py` — the routers are included at the bottom of server.py
after every name in this file's import list has been defined.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from server import (
    db,
    current_user,
    REFERRAL_REWARD,
    make_referral_code,
    referral_link_for,
)


router = APIRouter()


def _mask_email(e: str) -> str:
    if not e or "@" not in e:
        return "—"
    local, _, dom = e.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{dom}"
    return f"{local[:2]}***@{dom}"


async def _ensure_referral_code(u: dict) -> str:
    code = u.get("referral_code")
    if code:
        return code
    # Backfill for existing users
    for _ in range(5):
        c = make_referral_code()
        existing = await db.users.find_one({"referral_code": c}, {"_id": 0})
        if not existing:
            await db.users.update_one({"id": u["id"]}, {"$set": {"referral_code": c}})
            return c
    raise HTTPException(status_code=500, detail="Could not allocate referral code")


@router.get("/refer/validate")
async def refer_validate(code: str = Query(...)):
    """Validate a referral code. Public endpoint — used by the signup screen for inline feedback."""
    c = (code or "").strip().upper()
    if not c:
        return {"valid": True}
    owner = await db.users.find_one({"referral_code": c}, {"_id": 0})
    if not owner:
        return {"valid": False, "message": "Invalid referral code. Please check and try again."}
    if owner.get("account_status") and owner["account_status"] != "active":
        return {"valid": False, "message": "Invalid referral code. Please check and try again."}
    return {"valid": True, "owner_name": owner.get("name") or owner.get("email", "").split("@")[0]}


@router.get("/refer/me")
async def refer_me(u: dict = Depends(current_user)):
    """Return the current user's referral code, share link and tracking stats."""
    code = await _ensure_referral_code(u)
    refs = await db.referrals.find({"referrer_id": u["id"]}, {"_id": 0}).to_list(2000)
    total = len(refs)
    successful = sum(1 for r in refs if r.get("status") == "successful")
    pending = sum(1 for r in refs if r.get("status") == "pending")
    credits_earned = successful * REFERRAL_REWARD
    return {
        "code": code,
        "link": referral_link_for(code),
        "reward": REFERRAL_REWARD,
        "total": total,
        "successful": successful,
        "pending": pending,
        "credits_earned": credits_earned,
    }


@router.get("/refer/list")
async def refer_list(u: dict = Depends(current_user)):
    """Return the user's referrals (newest first). Emails are masked."""
    refs = await db.referrals.find({"referrer_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    referred_ids = [r.get("referred_id") for r in refs if r.get("referred_id")]
    users = await db.users.find(
        {"id": {"$in": referred_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}
    ).to_list(1000)
    um = {x["id"]: x for x in users}
    out = []
    for r in refs:
        ru = um.get(r.get("referred_id")) or {}
        out.append({
            "id": r["id"],
            "status": r.get("status"),
            "reward_credits": r.get("reward_credits", REFERRAL_REWARD),
            "created_at": r.get("created_at"),
            "completed_at": r.get("completed_at"),
            "name": ru.get("name") or "Friend",
            "email_masked": _mask_email(ru.get("email") or r.get("referred_email", "")),
        })
    return out
