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
    """Return the current user's referral code, share link and tracking stats.

    Iteration 57 status buckets:
      - pending    → referred user signed up but has not made their first deposit
      - qualified  → transient state (deposit made, reward being processed) — rarely observed
      - rewarded   → reward credited to referrer (legacy 'successful' is treated as rewarded)
      - rejected   → self-referral or blocked
    """
    code = await _ensure_referral_code(u)
    refs = await db.referrals.find({"referrer_id": u["id"]}, {"_id": 0}).to_list(2000)
    def _bucket(status: str) -> str:
        s = (status or "").lower()
        if s == "successful":
            return "rewarded"  # legacy alias
        return s
    total = len(refs)
    pending = sum(1 for r in refs if _bucket(r.get("status")) == "pending")
    qualified = sum(1 for r in refs if _bucket(r.get("status")) == "qualified")
    rewarded = sum(1 for r in refs if _bucket(r.get("status")) == "rewarded")
    rejected = sum(1 for r in refs if _bucket(r.get("status")) == "rejected")
    credits_earned = rewarded * REFERRAL_REWARD
    return {
        "code": code,
        "link": referral_link_for(code),
        "reward": REFERRAL_REWARD,
        "total": total,
        "pending": pending,
        "qualified": qualified,
        "rewarded": rewarded,
        "rejected": rejected,
        # Backwards-compat aliases (older frontends may still read `successful`).
        "successful": rewarded,
        "credits_earned": credits_earned,
    }


@router.get("/refer/list")
async def refer_list(u: dict = Depends(current_user)):
    """Return the user's referrals (newest first). Emails are masked."""
    refs = await db.referrals.find({"referrer_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    referred_ids = [r.get("referred_id") for r in refs if r.get("referred_id")]
    users = await db.users.find(
        {"id": {"$in": referred_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "total_deposits": 1, "role": 1}
    ).to_list(1000)
    um = {x["id"]: x for x in users}
    out = []
    for r in refs:
        ru = um.get(r.get("referred_id")) or {}
        raw_status = (r.get("status") or "").lower()
        display_status = "rewarded" if raw_status == "successful" else raw_status
        deposit_status = r.get("wallet_deposit_status") or ("completed" if display_status == "rewarded" else "pending")
        out.append({
            "id": r["id"],
            "status": display_status,
            "wallet_deposit_status": deposit_status,
            "reward_credits": r.get("reward_credits", REFERRAL_REWARD),
            "created_at": r.get("created_at"),
            "qualified_at": r.get("qualified_at"),
            "rewarded_at": r.get("rewarded_at"),
            "completed_at": r.get("completed_at"),
            "name": ru.get("name") or "Friend",
            "role": ru.get("role") or r.get("referred_role"),
            "email_masked": _mask_email(ru.get("email") or r.get("referred_email", "")),
        })
    return out


# ------------------- Referred-user view -------------------
@router.get("/refer/mine-inbound")
async def refer_mine_inbound(u: dict = Depends(current_user)):
    """Return the current user's own inbound referral (if they signed up using a code).

    Powers the 'Referred User View' from the Iteration 57 spec — displays:
      - referral_code (the code that was used)
      - referred_by  (name of referrer)
      - wallet_deposit_status (pending | completed)
      - referral_qualification_status (pending | rewarded | rejected)
    """
    inbound = await db.referrals.find_one({"referred_id": u["id"]}, {"_id": 0})
    if not inbound:
        return {"has_referral": False}
    referrer = await db.users.find_one({"id": inbound["referrer_id"]}, {"_id": 0, "name": 1, "email": 1})
    raw_status = (inbound.get("status") or "").lower()
    display_status = "rewarded" if raw_status == "successful" else raw_status
    return {
        "has_referral": True,
        "referral_code": inbound.get("code"),
        "referred_by": (referrer or {}).get("name") or _mask_email((referrer or {}).get("email", "")),
        "wallet_deposit_status": inbound.get("wallet_deposit_status") or ("completed" if display_status == "rewarded" else "pending"),
        "referral_qualification_status": display_status,
        "reward_credits": inbound.get("reward_credits", REFERRAL_REWARD),
        "created_at": inbound.get("created_at"),
        "rewarded_at": inbound.get("rewarded_at"),
    }
