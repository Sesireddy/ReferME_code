"""Wallet + Redemption endpoints — Phase C refactor.

URLs and behaviour preserved. Imports shared helpers + Pydantic models from server.py.
"""
from fastapi import APIRouter, Depends, HTTPException

from server import (
    db,
    current_user,
    require_role,
    require_phone_verified,
    push_notification,
    now_iso,
    new_id,
    get_action_cost,
    _credit_user,
    _upi_valid,
    _redemption_inr,
    FIRST_DEPOSIT_MIN_INR,
    FIRST_DEPOSIT_BONUS_PERCENT,
    FIRST_DEPOSIT_BONUS_MAX_CREDITS,
    MOCK_PAYMENTS_MODE,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    REDEMPTION_MIN_CREDITS,
    REDEMPTION_INR_PER_CREDIT,
    REFERRAL_REWARD,
    DepositBody,
    VerifyPaymentBody,
    RedemptionSubmitBody,
)

router = APIRouter()


def _compute_first_deposit_bonus(amount_inr: int) -> int:
    """Returns bonus credits for a first-ever deposit.

    Rule: If amount_inr >= FIRST_DEPOSIT_MIN_INR (₹200), award floor(amount_inr * 50%)
    bonus credits, capped at FIRST_DEPOSIT_BONUS_MAX_CREDITS (5000).
    Returns 0 if the amount is below the threshold.
    """
    if amount_inr < FIRST_DEPOSIT_MIN_INR:
        return 0
    bonus = (amount_inr * FIRST_DEPOSIT_BONUS_PERCENT) // 100
    return min(bonus, FIRST_DEPOSIT_BONUS_MAX_CREDITS)


# ------------------- Wallet -------------------
@router.get("/wallet")
async def get_wallet(u: dict = Depends(current_user)):
    txs = await db.transactions.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "credits": u.get("credits", 0),
        "locked_credits": u.get("locked_credits", 0),
        "free_uses_left": u.get("free_uses_left", 0),
        "total_deposits": u.get("total_deposits", 0),
        "action_cost": get_action_cost(u),
        "transactions": txs,
    }


@router.get("/subscription/plans")
async def subscription_plans(u: dict = Depends(current_user)):
    is_first = (u.get("total_deposits", 0) == 0)
    return {
        "free_tier": {
            "title": "Free Tier",
            "description": "1 referral application + 1 mock interview",
            "free_uses_left": u.get("free_uses_left", 0),
        },
        "paid_tier": {
            "title": "Paid Credits",
            "is_first_deposit": is_first,
            "first_deposit_inr": FIRST_DEPOSIT_MIN_INR,
            "first_deposit_bonus_percent": FIRST_DEPOSIT_BONUS_PERCENT,
            "first_deposit_bonus_max_credits": FIRST_DEPOSIT_BONUS_MAX_CREDITS,
            "subsequent_rate": "1 INR = 1 credit",
            "action_cost": get_action_cost(u),
        },
    }


# ------------------- Deposits (Razorpay) -------------------
@router.post("/wallet/deposit/create-order")
async def create_deposit_order(body: DepositBody, u: dict = Depends(require_role(["student", "professional", "employer"]))):
    if body.amount_inr < 1:
        raise HTTPException(status_code=400, detail="Amount must be ≥ ₹1")
    is_first = (u.get("total_deposits", 0) == 0)
    if is_first and body.amount_inr < FIRST_DEPOSIT_MIN_INR:
        raise HTTPException(status_code=400, detail=f"First deposit must be ≥ ₹{FIRST_DEPOSIT_MIN_INR}")
    order_id = f"order_{new_id()[:18]}"
    # Base credits: 1 INR = 1 credit for every deposit.
    base_credits = int(body.amount_inr)
    # First-deposit 50% bonus applies ONLY on the user's first-ever successful
    # deposit AND when amount ≥ FIRST_DEPOSIT_MIN_INR. Capped at 5000 credits.
    bonus_credits = _compute_first_deposit_bonus(body.amount_inr) if is_first else 0
    total_credits = base_credits + bonus_credits
    doc = {
        "id": new_id(),
        "razorpay_order_id": order_id,
        "user_id": u["id"],
        "amount_inr": body.amount_inr,
        "base_credits": base_credits,
        "bonus_credits": bonus_credits,
        "credits_to_grant": total_credits,
        "status": "created",
        "is_first_deposit": is_first,
        "mock": MOCK_PAYMENTS_MODE,
        "created_at": now_iso(),
    }
    await db.deposit_orders.insert_one(doc)
    return {
        "order_id": doc["id"],
        "razorpay_order_id": order_id,
        "amount_inr": body.amount_inr,
        "base_credits": base_credits,
        "bonus_credits": bonus_credits,
        "credits_to_grant": total_credits,
        "is_first_deposit": is_first,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "mock": MOCK_PAYMENTS_MODE,
    }


@router.post("/wallet/deposit/confirm")
async def confirm_deposit(body: VerifyPaymentBody, u: dict = Depends(current_user)):
    """In mock mode, accept any signature. In real mode, verify HMAC.

    Iteration 57: On a user's FIRST successful deposit, if they signed up via a
    referral code, the referrer receives +REFERRAL_REWARD credits and the referral
    row flips from `pending` → `rewarded`. See spec 'Referral Reward Policy'.
    """
    order = await db.deposit_orders.find_one({"razorpay_order_id": body.razorpay_order_id}, {"_id": 0})
    if not order or order["user_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "paid":
        return {"message": "Already credited", "credits": u["credits"]}
    if not MOCK_PAYMENTS_MODE:
        import hashlib
        import hmac
        msg = f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode()
        expected = hmac.new(RAZORPAY_KEY_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        if expected != body.razorpay_signature:
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Snapshot the pre-deposit total so we can detect the qualifying event for referrals.
    fresh_u = await db.users.find_one({"id": u["id"]}, {"_id": 0}) or {}
    is_first_deposit = int(fresh_u.get("total_deposits", 0) or 0) == 0

    await db.deposit_orders.update_one(
        {"id": order["id"]},
        {"$set": {"status": "paid", "razorpay_payment_id": body.razorpay_payment_id, "updated_at": now_iso()}},
    )
    # Split credit into base deposit and (optional) first-deposit bonus so users
    # see two distinct transactions in their history.
    base_credits = int(order.get("base_credits") or order.get("credits_to_grant") or 0)
    bonus_credits = int(order.get("bonus_credits") or 0)
    # Guard against legacy orders where base+bonus was not split.
    if base_credits == 0 and bonus_credits == 0:
        base_credits = int(order.get("credits_to_grant") or 0)

    new_balance = await _credit_user(
        u["id"],
        base_credits,
        "deposit",
        {"order_id": order["id"], "amount_inr": order["amount_inr"], "label": "Top up"},
    )
    if bonus_credits > 0:
        new_balance = await _credit_user(
            u["id"],
            bonus_credits,
            "first_deposit_bonus",
            {
                "order_id": order["id"],
                "amount_inr": order["amount_inr"],
                "bonus_percent": FIRST_DEPOSIT_BONUS_PERCENT,
                "label": f"First Deposit Bonus ({FIRST_DEPOSIT_BONUS_PERCENT}%)",
            },
        )
    credits_added = base_credits + bonus_credits
    await db.users.update_one({"id": u["id"]}, {"$inc": {"total_deposits": 1}})
    if bonus_credits > 0:
        await push_notification(
            u["id"],
            "First Deposit Bonus 🎉",
            f"+{credits_added} credits added ({base_credits} + {bonus_credits} bonus).",
            "success",
        )
    else:
        await push_notification(u["id"], "Credits added 💰", f"+{credits_added} credits added to your wallet.", "success")

    # ---------- Referral reward (fires ONCE on the qualifying first successful deposit) ----------
    referral_awarded = False
    if is_first_deposit and fresh_u.get("referred_by"):
        pending = await db.referrals.find_one(
            {"referred_id": u["id"], "status": "pending"}, {"_id": 0}
        )
        if pending:
            referrer = await db.users.find_one({"id": pending["referrer_id"]}, {"_id": 0})
            same_email = referrer and referrer.get("email", "").lower() == (u.get("email") or "").lower()
            if not referrer or same_email:
                # Self-referral or missing referrer — mark rejected so it never rewards.
                await db.referrals.update_one(
                    {"id": pending["id"]},
                    {"$set": {
                        "status": "rejected",
                        "reason": "self_referral" if same_email else "referrer_missing",
                        "wallet_deposit_status": "completed",
                        "completed_at": now_iso(),
                    }},
                )
            else:
                # Atomic transition pending → rewarded so a race can't double-pay.
                res = await db.referrals.update_one(
                    {"id": pending["id"], "status": "pending"},
                    {"$set": {
                        "status": "rewarded",
                        "wallet_deposit_status": "completed",
                        "qualified_at": now_iso(),
                        "rewarded_at": now_iso(),
                        "completed_at": now_iso(),
                        "reward_credits": REFERRAL_REWARD,
                    }},
                )
                if res.modified_count == 1:
                    await _credit_user(
                        referrer["id"],
                        REFERRAL_REWARD,
                        "referral_reward",
                        {
                            "label": f"Referral Bonus · {u.get('name') or u.get('email')}",
                            "referred_id": u["id"],
                            "referral_id": pending["id"],
                            "deposit_order_id": order["id"],
                        },
                    )
                    referral_awarded = True
                    await push_notification(
                        referrer["id"],
                        "Referral Bonus Credited 🎉",
                        f"Congratulations! Your referral bonus of {REFERRAL_REWARD} credits has been credited to your wallet.",
                        "success",
                    )
                    await push_notification(
                        u["id"],
                        "First deposit successful ✅",
                        "Your first wallet deposit was successful. Your referrer has received the referral reward.",
                        "success",
                    )
    return {
        "message": "Payment confirmed",
        "credits": new_balance,
        "added": credits_added,
        "base_credits": base_credits,
        "bonus_credits": bonus_credits,
        "first_deposit_bonus_applied": bonus_credits > 0,
        "referral_awarded": referral_awarded,
    }


# ------------------- Redemption (Pro-side) -------------------
@router.post("/redemption/submit")
async def submit_redemption(
    body: RedemptionSubmitBody,
    u: dict = Depends(require_role(["professional"])),
):
    await require_phone_verified(u)
    if not _upi_valid(body.upi_id):
        raise HTTPException(status_code=400, detail="Please enter a valid UPI ID (e.g. name@bank)")
    if body.credits < REDEMPTION_MIN_CREDITS:
        raise HTTPException(status_code=400, detail=f"Minimum {REDEMPTION_MIN_CREDITS} credits are required to submit a redemption request.")
    avail = u.get("credits", 0)
    if body.credits > avail:
        raise HTTPException(status_code=400, detail="Redemption amount exceeds available credits.")

    req_id = new_id()
    now = now_iso()
    # Atomically deduct from credits and increment locked_credits
    upd = await db.users.find_one_and_update(
        {"id": u["id"], "credits": {"$gte": body.credits}},
        {"$inc": {"credits": -body.credits, "locked_credits": body.credits}},
        return_document=True,
        projection={"_id": 0, "credits": 1, "locked_credits": 1},
    )
    if not upd:
        raise HTTPException(status_code=400, detail="Available credits changed. Please refresh and try again.")

    doc = {
        "id": req_id,
        "pro_id": u["id"],
        "pro_name": u.get("name") or u.get("full_name") or u.get("email", ""),
        "pro_email": u.get("email", ""),
        "credits_requested": body.credits,
        "amount_inr": _redemption_inr(body.credits),
        "available_credits_at_request": avail,
        "account_holder_name": body.account_holder_name.strip(),
        "upi_id": body.upi_id.strip(),
        "bank_account": (body.bank_account or "").strip(),
        "ifsc": (body.ifsc or "").strip().upper(),
        "status": "pending",  # pending | approved | paid | rejected
        "payment_ref": "",
        "payment_date": "",
        "remarks": "",
        "rejection_reason": "",
        "created_at": now,
        "updated_at": now,
        "approved_at": "",
        "paid_at": "",
        "rejected_at": "",
    }
    await db.redemption_requests.insert_one(doc)

    # Ledger entry for traceability
    await db.transactions.insert_one({
        "id": new_id(),
        "user_id": u["id"],
        "delta": -body.credits,
        "reason": "redemption_locked",
        "meta": {"request_id": req_id, "upi_id": body.upi_id, "amount_inr": doc["amount_inr"]},
        "created_at": now,
    })

    await push_notification(
        u["id"],
        "Redemption requested 🕒",
        f"Your request to redeem {body.credits} credits (₹{doc['amount_inr']:.2f}) is pending approval.",
        "info",
    )
    doc.pop("_id", None)
    return doc


@router.get("/redemption/my")
async def my_redemptions(u: dict = Depends(require_role(["professional"]))):
    items = await db.redemption_requests.find(
        {"pro_id": u["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"items": items, "min_credits": REDEMPTION_MIN_CREDITS, "inr_per_credit": REDEMPTION_INR_PER_CREDIT}
