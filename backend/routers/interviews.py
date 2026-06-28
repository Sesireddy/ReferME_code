"""Mock Interview endpoints — Phase B refactor.

URLs and behaviour preserved. Imports shared helpers + Pydantic models from server.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from server import (
    db,
    current_user,
    require_role,
    require_phone_verified,
    push_notification,
    now_iso,
    new_id,
    compute_resume_score,
    recalc_tps_for_user,
    INTERVIEW_PRO_REWARD,
    SLOT_MIN_DURATION_MIN,
    SLOT_MAX_HOURS_PER_DAY,
    JITSI_BASE,
    ACTION_COST,
    _can_use_free,
    _credit_user,
    _build_candidate_summary,
    build_interview_ics,
    _booking_email_html,
    send_html_email,
    InterviewSlotBody,
    BookInterviewBody,
    CompleteInterviewBody,
)


router = APIRouter()


@router.post("/interviews/slots")
async def create_slot(body: InterviewSlotBody, u: dict = Depends(require_role(["professional"]))):
    await require_phone_verified(u)
    if not u.get("is_email_verified"):
        raise HTTPException(status_code=403, detail="Verify your email before posting interview slots.")
    if not u.get("gmail_verified"):
        raise HTTPException(
            status_code=403,
            detail="Gmail verification is required before creating a Mock Interview slot.",
        )
    if not (body.skill_set or []):
        raise HTTPException(status_code=400, detail="Skill Set is required.")
    try:
        start = datetime.fromisoformat(body.start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(body.end_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    if end <= start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    duration_min = (end - start).total_seconds() / 60
    if duration_min < SLOT_MIN_DURATION_MIN:
        raise HTTPException(status_code=400, detail=f"Slot must be at least {SLOT_MIN_DURATION_MIN} minutes")
    if duration_min > SLOT_MAX_HOURS_PER_DAY * 60:
        raise HTTPException(status_code=400, detail=f"Single slot cannot exceed {SLOT_MAX_HOURS_PER_DAY} hours")
    # Session duration must be a multiple of 30 minutes — required for the auto-split rule.
    if int(duration_min) % 30 != 0:
        raise HTTPException(
            status_code=400,
            detail="Interview slot duration must be a multiple of 30 minutes (e.g. 30, 60, 90, 120 min).",
        )
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Slot must be in the future")

    # Daily 5-hour total cap for this pro
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    existing = await db.interview_slots.find(
        {"pro_id": u["id"], "status": {"$in": ["available", "booked"]}},
        {"_id": 0},
    ).to_list(500)
    day_hours = 0.0
    for s in existing:
        try:
            es = datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
            ee = datetime.fromisoformat(s["end_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        # Conflict check
        if start < ee and end > es:
            raise HTTPException(
                status_code=400,
                detail=f"Conflicts with existing slot {es.strftime('%d %b %H:%M')} – {ee.strftime('%H:%M')}",
            )
        # Daily total accumulation
        if day_start <= es < day_end:
            day_hours += (ee - es).total_seconds() / 3600
    if day_hours + duration_min / 60 > SLOT_MAX_HOURS_PER_DAY:
        raise HTTPException(
            status_code=400,
            detail=f"Daily limit {SLOT_MAX_HOURS_PER_DAY}h exceeded (already booked {day_hours:.1f}h on this day).",
        )

    # ----------------------------- Auto-split into 30-min sub-slots -----------------------------
    # One session = N child slots. All children share `session_id`. Each child has its own
    # meeting_url so that bookings stay isolated per 30-min window.
    session_id = new_id()
    pro_name = u.get("name") or u["email"].split("@")[0]
    sub_slots: list[dict] = []
    cursor = start
    while cursor < end:
        sub_end = cursor + timedelta(minutes=30)
        slot_id = new_id()
        meeting_url = f"{JITSI_BASE}/ReferME-{slot_id.split('-')[0]}"
        sub_slots.append({
            "id": slot_id,
            "session_id": session_id,
            "pro_id": u["id"],
            "pro_name": pro_name,
            "start_at": cursor.isoformat().replace("+00:00", "Z"),
            "end_at": sub_end.isoformat().replace("+00:00", "Z"),
            "scheduled_at": cursor.isoformat().replace("+00:00", "Z"),  # legacy alias
            "skill_set": body.skill_set or [],
            "experience_years": body.experience_years or 0,
            "topic": body.topic or "",
            "status": "available",
            "student_id": None,
            "student_name": None,
            "meeting_url": meeting_url,
            "created_at": now_iso(),
        })
        cursor = sub_end
    await db.interview_slots.insert_many(sub_slots)
    # Build a response shape that's both new (session-aware) AND backwards-compatible
    # with callers that read `id`/`start_at`/`end_at` at the top level.
    first = sub_slots[0]
    last = sub_slots[-1]
    return {
        # Legacy/back-compat shim (the FIRST sub-slot's id, plus full session bounds):
        "id": first["id"],
        "start_at": body.start_at,
        "end_at": body.end_at,
        "skill_set": first["skill_set"],
        "experience_years": first["experience_years"],
        "topic": first["topic"],
        "status": "available",
        "meeting_url": first["meeting_url"],
        "pro_id": first["pro_id"],
        "pro_name": first["pro_name"],
        # New session-aware fields:
        "session_id": session_id,
        "slot_count": len(sub_slots),
        "session_start_at": first["start_at"],
        "session_end_at": last["end_at"],
        "slots": [{k: v for k, v in s.items() if k != "_id"} for s in sub_slots],
    }


@router.get("/interviews/slots")
async def list_slots(
    pro_id: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    date: Optional[str] = Query(None),  # YYYY-MM-DD — only slots starting on this date
    category: Optional[str] = Query(None),  # fresher | experienced
    u: dict = Depends(current_user),
):
    q: dict = {}
    if pro_id:
        q["pro_id"] = pro_id
    if u["role"] == "professional":
        q["pro_id"] = u["id"]
    elif u["role"] == "student" and not pro_id:
        q["status"] = "available"
    if skill:
        q["skill_set"] = {"$regex": skill, "$options": "i"}
    slots = await db.interview_slots.find(q, {"_id": 0}).sort("start_at", 1).to_list(500)
    # Apply date / category / future-only filters (students never see expired slots).
    out = []
    now_dt = datetime.now(timezone.utc)
    for s in slots:
        try:
            sd = datetime.fromisoformat((s.get("start_at") or s.get("scheduled_at") or "").replace("Z", "+00:00"))
        except Exception:
            sd = None
        # Students:
        #   - Listing only (no pro_id): hide expired AND only show available (top-level filter).
        #   - When pro_id is supplied (drill-down view), show the FULL grid for that pro —
        #     available + booked — but still hide expired slots.
        if u["role"] == "student":
            if not sd or sd <= now_dt:
                continue
            if not pro_id and s.get("status") != "available":
                continue
            if pro_id and s.get("status") == "cancelled":
                continue
        # Professionals: keep "Your slots" actionable only.
        #   - Hide `available` slots whose end_at has already passed (expired without a booking).
        #   - Hide `completed` slots (they live in Profile → My Mock Interviews → Completed).
        #   - Hide `cancelled` slots from this view too.
        #   - All `booked` slots stay until the pro marks them as Done.
        if u["role"] == "professional" and not pro_id:
            status_now = s.get("status")
            if status_now in ("completed", "cancelled"):
                continue
            if status_now == "available":
                try:
                    ed = datetime.fromisoformat((s.get("end_at") or "").replace("Z", "+00:00"))
                except Exception:
                    ed = None
                if ed and ed <= now_dt:
                    continue
        if date and sd:
            if sd.strftime("%Y-%m-%d") != date:
                continue
        if category in ("fresher", "experienced"):
            slot_cat = "experienced" if int(s.get("experience_years") or 0) > 0 else "fresher"
            if slot_cat != category:
                continue
        # Strip sensitive fields when surfacing to students (the booked student_id stays
        # opaque so other students can't profile bookings).
        if u["role"] == "student" and s.get("status") == "booked":
            s = {**s, "student_id": None, "student_name": None}
        out.append(s)
    return out


@router.post("/interviews/book")
async def book_interview(body: BookInterviewBody, u: dict = Depends(require_role(["student"]))):
    # ---- Overlap check: prevent multiple bookings for the same/overlapping time period ----
    target = await db.interview_slots.find_one(
        {"id": body.slot_id},
        {"_id": 0, "start_at": 1, "end_at": 1, "status": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Slot not found")
    if target.get("status") != "available":
        raise HTTPException(status_code=400, detail="Slot not available")
    new_start = target.get("start_at", "")
    new_end = target.get("end_at", "")
    if new_start and new_end:
        # Overlap: existing.start < new.end AND existing.end > new.start
        conflict = await db.interview_bookings.find_one({
            "student_id": u["id"],
            "status": {"$in": ["booked", "completed"]},
            "start_at": {"$lt": new_end},
            "end_at": {"$gt": new_start},
        })
        if conflict:
            raise HTTPException(
                status_code=409,
                detail="You already have a mock interview scheduled during this time. Please select a different time slot.",
            )

    # Atomic claim: only one student can flip available -> booked.
    booked_at_iso = now_iso()
    res = await db.interview_slots.find_one_and_update(
        {"id": body.slot_id, "status": "available"},
        {
            "$set": {
                "status": "booked",
                "student_id": u["id"],
                "student_name": u.get("name") or u["email"].split("@")[0],
                "student_email": u.get("email"),
                "booked_at": booked_at_iso,
            }
        },
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        # Either non-existent or already taken by someone else (race-safe).
        raise HTTPException(status_code=400, detail="Slot not available")
    slot = res
    use_free = _can_use_free(u, "interview")
    if not use_free and u.get("credits", 0) < ACTION_COST:
        # Roll back the booking since the user can't pay for it.
        await db.interview_slots.update_one(
            {"id": slot["id"]},
            {"$set": {"status": "available", "student_id": None, "student_name": None, "student_email": None, "booked_at": None}},
        )
        raise HTTPException(status_code=400, detail="Insufficient credits. Please add credits to continue booking this interview.")
    if use_free:
        await db.users.update_one({"id": u["id"]}, {"$inc": {"free_uses_left": -1}})
    else:
        await _credit_user(u["id"], -ACTION_COST, "interview_booking", {"slot_id": slot["id"]})
    pro = await db.users.find_one({"id": slot["pro_id"]}, {"_id": 0, "password_hash": 0})
    when = slot.get("start_at", "")
    end_when = slot.get("end_at", "")
    # In-app notifications
    await push_notification(u["id"], "Interview booked ✅", f"With {slot['pro_name']} at {when}", "success")
    await push_notification(slot["pro_id"], "New interview booked", f"Student booked your slot at {when}", "info")
    # Email both parties — with .ics calendar attachment
    meeting = slot.get("meeting_url", "")
    student_name = u.get("name") or u["email"].split("@")[0]
    candidate_summary = _build_candidate_summary(u)
    ics_bytes = build_interview_ics(
        summary=f"ReferME Mock Interview — {slot['pro_name']} & {student_name}",
        description=f"Skill Set: {', '.join(slot.get('skill_set', []) or []) or '—'}\\nMeeting link: {meeting}",
        location=meeting,
        start_iso=when,
        end_iso=end_when,
        uid=slot["id"],
    )
    student_html = _booking_email_html(role="student", slot=slot, candidate=u, pro=pro, meeting=meeting, candidate_summary=candidate_summary)
    pro_html = _booking_email_html(role="pro", slot=slot, candidate=u, pro=pro, meeting=meeting, candidate_summary=candidate_summary)
    student_sent = await send_html_email(
        u["email"], "ReferME · Mock Interview confirmed", student_html,
        mock_purpose="booking_student",
        attachments=[{"filename": "invite.ics", "content_bytes": ics_bytes, "mime_type": "text/calendar"}],
    )
    pro_sent = False
    if pro and pro.get("email"):
        pro_sent = await send_html_email(
            pro["email"], "ReferME · New Mock Interview booking", pro_html,
            mock_purpose="booking_pro",
            attachments=[{"filename": "invite.ics", "content_bytes": ics_bytes, "mime_type": "text/calendar"}],
        )
    # Persist booking record for admin tracking + email delivery audit
    await db.interview_bookings.insert_one({
        "id": new_id(),
        "slot_id": slot["id"],
        "session_id": slot.get("session_id"),
        "pro_id": slot["pro_id"],
        "pro_name": slot.get("pro_name"),
        "pro_email": (pro or {}).get("email"),
        "student_id": u["id"],
        "student_name": student_name,
        "student_email": u.get("email"),
        "start_at": when,
        "end_at": end_when,
        "skill_set": slot.get("skill_set", []),
        "meeting_url": meeting,
        "booked_at": booked_at_iso,
        "status": "booked",
        "student_email_status": "sent" if student_sent else "queued",
        "pro_email_status": "sent" if pro_sent else "queued",
    })
    return {"message": "Booked", "used_free": use_free, "meeting_url": meeting,
            "student_email_status": "sent" if student_sent else "queued",
            "pro_email_status": "sent" if pro_sent else "queued"}


@router.get("/interviews/my-bookings")
async def my_bookings(
    upcoming_only: bool = Query(True),
    u: dict = Depends(current_user),
):
    """Return slots the current user has booked (student) or is conducting (pro).
    Used by dashboards to surface 'Join video' CTAs for upcoming sessions.
    """
    if u["role"] == "student":
        q = {"student_id": u["id"]}
    elif u["role"] == "professional":
        q = {"pro_id": u["id"], "student_id": {"$ne": None}}
    else:
        return []
    slots = await db.interview_slots.find(q, {"_id": 0}).sort("start_at", 1).to_list(500)
    now_dt = datetime.now(timezone.utc)
    out = []
    for s in slots:
        # Spec: proof screenshot is visible only to Admin + Working Professional
        if u["role"] == "student":
            s.pop("proof_screenshot", None)
        try:
            sd = datetime.fromisoformat((s.get("start_at") or "").replace("Z", "+00:00"))
            ed = datetime.fromisoformat((s.get("end_at") or "").replace("Z", "+00:00"))
        except Exception:
            sd, ed = None, None
        # Only consider booked or completed within last 24h
        if upcoming_only:
            if s.get("status") in ("cancelled",):
                continue
            if ed and ed < now_dt - timedelta(hours=2):
                continue
        # Hydrate with counterparty name
        if u["role"] == "student":
            s["counterparty_name"] = s.get("pro_name")
        else:
            s["counterparty_name"] = s.get("student_name")
        # Join window: enabled 10 min before start until 2h after end
        s["join_enabled"] = False
        if sd and ed:
            window_start = sd - timedelta(minutes=10)
            window_end = ed + timedelta(hours=2)
            s["join_enabled"] = window_start <= now_dt <= window_end
        # Has the scheduled session ended (used by Pro 'My Mock Interviews' to swap CTAs)?
        s["slot_ended"] = bool(ed and ed <= now_dt)
        # Did BOTH the pro and the student actually click 'Join' during the window?
        joined_by = set(s.get("joined_by") or [])
        student_id = s.get("student_id")
        s["both_joined"] = bool(student_id) and (s["pro_id"] in joined_by) and (student_id in joined_by)
        # Strip the internal joined_by list from the response (not needed by clients)
        s.pop("joined_by", None)
        out.append(s)
    return out


@router.post("/interviews/{slot_id}/complete")
async def complete_interview(
    slot_id: str,
    body: CompleteInterviewBody,
    u: dict = Depends(require_role(["professional"])),
):
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot or slot["pro_id"] != u["id"]:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["status"] != "booked":
        raise HTTPException(status_code=400, detail="Slot not booked")
    if not slot.get("student_id"):
        raise HTTPException(status_code=400, detail="No candidate booked for this slot")
    # Spec rule: allow completion once the scheduled start time has passed (no join-required gate).
    try:
        sd = datetime.fromisoformat((slot.get("start_at") or "").replace("Z", "+00:00"))
    except Exception:
        sd = None
    now_dt = datetime.now(timezone.utc)
    if sd and now_dt < sd:
        raise HTTPException(
            status_code=400,
            detail="Interview cannot be marked completed before the scheduled start time.",
        )
    # Field-level guards (Pydantic also enforces, but produce friendly messages)
    if not body.feedback or len(body.feedback.strip()) < 20:
        raise HTTPException(status_code=400, detail="Please provide feedback for the candidate.")
    if not body.proof_screenshot:
        raise HTTPException(
            status_code=400,
            detail="Please upload interview proof before marking the interview as completed.",
        )
    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$set": {
            "status": "completed",
            "completed_at": now_iso(),
            "candidate_rating": body.rating,
            "candidate_feedback": body.feedback.strip(),
            "proof_screenshot": body.proof_screenshot,
        }},
    )
    # Pro reward
    await _credit_user(u["id"], INTERVIEW_PRO_REWARD, "mock_interview_reward", {
        "slot_id": slot_id,
        "candidate_id": slot["student_id"],
        "rating": body.rating,
    })
    # Increment student interviews_attended, aggregate student_rating, refresh resume/TPS
    student = await db.users.find_one_and_update(
        {"id": slot["student_id"]},
        {"$inc": {"interviews_attended": 1}},
        return_document=True,
        projection={"_id": 0},
    )
    if student:
        # Aggregate student rating (1-10) — running average
        prev_sr_count = int(student.get("student_ratings_count") or 0)
        prev_sr_avg = float(student.get("student_rating") or 0)
        new_sr_count = prev_sr_count + 1
        new_sr_avg = round(((prev_sr_avg * prev_sr_count) + float(body.rating)) / new_sr_count, 2)
        new_score = compute_resume_score(student)
        new_profile = {**(student.get("profile", {}) or {}), "resume_score": new_score}
        await db.users.update_one(
            {"id": student["id"]},
            {
                "$set": {
                    "profile": new_profile,
                    "student_rating": new_sr_avg,
                    "student_ratings_count": new_sr_count,
                }
            },
        )
        # Recalculate TPS now that resume_score, interviews_attended and student_rating are fresh
        await recalc_tps_for_user(student["id"])
        await push_notification(
            student["id"],
            "Interview completed 🎓",
            f"Your interviewer rated you {body.rating}/10. Resume score: {new_score}/100.",
            "success",
        )
    # Aggregate pro rating: store running average and total ratings count
    pro = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    prev_count = int(pro.get("ratings_count") or 0)
    prev_avg = float(pro.get("rating") or 0)
    new_count = prev_count + 1
    new_avg = round(((prev_avg * prev_count) + body.rating) / new_count, 2)
    await db.users.update_one(
        {"id": u["id"]},
        {
            "$inc": {"interviews_conducted": 1, "ratings_count": 1},
            "$set": {"rating": new_avg},
        },
    )
    await push_notification(
        u["id"],
        f"Earned +{INTERVIEW_PRO_REWARD} credits 🎯",
        f"Interview marked completed. Your rating: {new_avg}/10 ({new_count} interviews).",
        "success",
    )
    return {"message": "Completed", "earned": INTERVIEW_PRO_REWARD, "pro_rating": new_avg, "candidate_rating": body.rating}


@router.post("/interviews/{slot_id}/joined")
async def mark_interview_joined(slot_id: str, u: dict = Depends(current_user)):
    """Frontend hits this when the user actually opens the Jitsi room.
    Used by complete_interview to verify both parties showed up.
    """
    slot = await db.interview_slots.find_one({"id": slot_id}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if u["id"] not in (slot["pro_id"], slot.get("student_id")):
        raise HTTPException(status_code=403, detail="Not your session")
    await db.interview_slots.update_one(
        {"id": slot_id},
        {"$addToSet": {"joined_by": u["id"]}},
    )
    return {"message": "Joined"}


