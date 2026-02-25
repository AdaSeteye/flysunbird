import uuid
from urllib.parse import quote
from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
from app.db.session import get_db
from app.api.deps import require_roles
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.audit_log import AuditLog
from app.models.pilot import PilotAssignment
from app.models.user import User
from app.models.time_entry import TimeEntry
from app.models.route import Route
from app.models.location import Location
from app.schemas.location import LocationIn, LocationPatch
from app.models.slot_rule import SlotRule
from app.models.passenger import Passenger
from app.models.cancellation import Cancellation
from app.services.email_service import queue_email
from app.services.audit_service import log_audit
from app.api.v1.routes.payments import _generate_ticket_for_booking
from app.schemas.ops import TimeEntryIn, TimeEntryOut, SlotRuleIn, SlotRuleOut, CancellationRequestIn, CancellationDecisionIn, DashboardMetrics, DashboardSeriesPoint, WeeklyPlanImportRequest, WeeklyPlanImportResponse
from app.services.weekly_plan_service import import_weekly_plan, get_preset_legs, PRESETS

router = APIRouter(tags=["ops"])
class MoveBookingIn(BaseModel):
    target: str = ""
    reason: str = ""

class RefundIn(BaseModel):
    amount: int = 0
    reason: str = ""

class ResendTicketIn(BaseModel):
    reason: str = ""




# -------------------------
# OPS: CREATE DRAFT BOOKING (book on behalf of customer)
# -------------------------
class OpsDraftBookingIn(BaseModel):
    timeEntryId: str
    pax: int = 1
    bookerEmail: str
    bookerName: str = ""
    passengers: list[dict] = []
    currency: str = "USD"            # USD|TZS
    exchangeRate: int | None = None  # USD->TZS used (optional override)

@router.post("/ops/bookings/create-draft")
def ops_create_draft_booking(body: OpsDraftBookingIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    # create or get booker user
    booker = db.query(User).filter(User.email == body.bookerEmail.lower()).first()
    if not booker:
        from app.core.security import hash_password
        booker = User(
            id=str(uuid.uuid4()),
            email=body.bookerEmail.lower(),
            full_name=body.bookerName or "",
            role="customer",
            password_hash=hash_password(str(uuid.uuid4())),
            is_active=True,
        )
        db.add(booker)
        db.commit()
    # reserve seats + create booking
    from app.services.booking_service import create_booking
    booking = create_booking(db, body.timeEntryId, booker, body.pax, body.passengers)

    # mark as DRAFT + ops created
    booking.status = "DRAFT"
    booking.payment_status = "unpaid"
    booking.created_by_role = "OPS"
    booking.currency = body.currency
    booking.exchange_rate_used = body.exchangeRate
    log_audit(db, user.id, "booking.create_draft", "booking", booking.id, {"booking_ref": booking.booking_ref, "currency": body.currency, "exchangeRate": body.exchangeRate})
    db.commit()
    return {"bookingRef": booking.booking_ref, "status": booking.status, "paymentStatus": booking.payment_status}

# -------------------------
# BOOKINGS
# -------------------------
@router.get("/ops/bookings")
def list_bookings(
    q: str = "",
    status: str = "",
    payment_status: str = "",
    dateStr: str = "",
    route_id: str = "",
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    query = (
        db.query(Booking, TimeEntry, Route, User)
        .join(TimeEntry, TimeEntry.id == Booking.time_entry_id)
        .join(Route, Route.id == TimeEntry.route_id)
        .outerjoin(User, User.id == Booking.user_id)
    )
    if q:
        query = query.filter(Booking.booking_ref.ilike(f"%{q}%"))
    if status:
        query = query.filter(Booking.status == status)
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status)
    if dateStr:
        query = query.filter(TimeEntry.date_str == dateStr)
    if route_id:
        query = query.filter(TimeEntry.route_id == route_id)

    rows = query.order_by(Booking.created_at.desc()).limit(min(max(limit, 1), 1000)).all()
    return [{
        "bookingRef": b.booking_ref,
        "status": b.status,
        "paymentStatus": b.payment_status,
        "pax": b.pax,
        "timeEntryId": b.time_entry_id,
        "createdAt": b.created_at.isoformat(),
        "from": route.from_label,
        "to": route.to_label,
        "dateStr": te.date_str,
        "contactEmail": user.email if user else None,
        "contactName": user.full_name if user else None,
    } for b, te, route, user in rows]

@router.get("/ops/bookings/{booking_ref}")
def booking_detail(
    booking_ref: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    te = db.get(TimeEntry, b.time_entry_id)
    booker = db.get(User, b.user_id) if b.user_id else None
    route = db.get(Route, te.route_id) if te else None
    pax = db.query(Passenger).filter(Passenger.booking_id == b.id).all()
    pays = db.query(Payment).filter(Payment.booking_id == b.id).order_by(Payment.created_at.desc()).all()
    return {
        "bookingRef": b.booking_ref,
        "status": b.status,
        "paymentStatus": b.payment_status,
        "pax": b.pax,
        "holdExpiresAt": b.hold_expires_at.isoformat() if b.hold_expires_at else None,
        "createdAt": b.created_at.isoformat(),
        "from": route.from_label if route else None,
        "to": route.to_label if route else None,
        "dateStr": te.date_str if te else None,
        "contactEmail": booker.email if booker else None,
        "contactName": booker.full_name if booker else None,
        "timeEntry": {
            "id": te.id if te else b.time_entry_id,
            "routeId": te.route_id if te else None,
            "dateStr": te.date_str if te else None,
            "start": te.start if te else None,
            "end": te.end if te else None,
            "priceUSD": te.price_usd if te else None,
            "seatsAvailable": te.seats_available if te else None,
            "flightNo": te.flight_no if te else None,
            "cabin": te.cabin if te else None,
        },
        "passengers": [{
            "first": p.first, "last": p.last, "phone": p.phone, "gender": p.gender,
            "dob": p.dob, "nationality": p.nationality, "idType": p.id_type, "idNumber": p.id_number
        } for p in pax],
        "payments": [{
            "provider": p.provider, "status": p.status, "amountUSD": p.amount_usd, "currency": p.currency,
            "providerRef": p.provider_ref, "createdAt": p.created_at.isoformat()
        } for p in pays],

        "audit": [{
            "at": a.created_at.isoformat(),
            "action": a.action,
            "actor": a.actor_user_id,
            "details": a.details_json,
        } for a in db.query(AuditLog).filter(AuditLog.entity_type == "booking", AuditLog.entity_id == b.booking_ref).order_by(AuditLog.created_at.asc()).all()],

    }

@router.post("/ops/bookings/{booking_ref}/mark-paid")
def mark_paid(
    booking_ref: str,
    pilot_email: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b.payment_status == "paid":
        return {"ok": True, "status": "already_paid"}

    b.payment_status = "paid"
    b.status = "CONFIRMED"
    db.add(Payment(
        id=str(uuid.uuid4()),
        booking_id=b.id,
        provider="manual",
        amount_usd=0,
        currency="USD",
        status="paid",
        provider_ref=f"manual:{user.email}:{datetime.now(timezone.utc).isoformat()}",
    ))
    log_audit(db, user.id, "booking.mark_paid", "booking", b.id, {"bookingRef": b.booking_ref})

    # Generate ticket PDF with QR code (scan → open PDF) so user can view ticket after mark paid
    try:
        _generate_ticket_for_booking(db, b)
    except Exception:
        pass  # non-fatal; ticket can be generated later or via resend

    if pilot_email:
        pilot_user = db.query(User).filter(User.email == pilot_email.strip().lower(), User.role == "pilot").first()
        if pilot_user:
            exists = db.query(PilotAssignment).filter(
                PilotAssignment.time_entry_id == b.time_entry_id,
                PilotAssignment.pilot_user_id == pilot_user.id,
            ).first()
            if not exists:
                pa = PilotAssignment(
                    id=str(uuid.uuid4()),
                    time_entry_id=b.time_entry_id,
                    pilot_user_id=pilot_user.id,
                    status="assigned",
                )
                db.add(pa)
                log_audit(db, user.id, "pilot_assignment_created", "pilot_assignment", pa.id, {"pilot_email": pilot_email})
        subject = f"FlySunbird: Paid booking {b.booking_ref}"
        body = f"Booking {b.booking_ref} is PAID/CONFIRMED. Booker ref: {b.booking_ref}. Time entry: {b.time_entry_id}."
        queue_email(db, pilot_email, subject, body, related_booking_ref=b.booking_ref)
        log_audit(db, user.id, "pilot.email_sent", "booking", b.id, {"to": pilot_email})

    db.commit()
    return {"ok": True, "bookingRef": b.booking_ref, "status": b.status, "paymentStatus": b.payment_status}


class AssignPilotIn(BaseModel):
    pilot_email: str = ""


@router.post("/ops/bookings/{booking_ref}/assign-pilot")
def assign_pilot_to_booking(
    booking_ref: str,
    body: AssignPilotIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops", "admin", "superadmin")),
):
    """Assign a pilot to a paid booking's flight (creates PilotAssignment). Use for Cybersource-paid bookings."""
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if (b.payment_status or "").lower() != "paid":
        raise HTTPException(status_code=400, detail="Can only assign pilot to paid bookings")
    email = (body.pilot_email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="pilot_email required")
    pilot_user = db.query(User).filter(User.email == email, User.role == "pilot").first()
    if not pilot_user:
        raise HTTPException(status_code=404, detail=f"No pilot user found with email {email}")
    exists = db.query(PilotAssignment).filter(
        PilotAssignment.time_entry_id == b.time_entry_id,
        PilotAssignment.pilot_user_id == pilot_user.id,
    ).first()
    if exists:
        return {"ok": True, "alreadyAssigned": True, "assignmentId": exists.id}
    pa = PilotAssignment(
        id=str(uuid.uuid4()),
        time_entry_id=b.time_entry_id,
        pilot_user_id=pilot_user.id,
        status="assigned",
    )
    db.add(pa)
    log_audit(db, user.id, "pilot_assignment_created", "pilot_assignment", pa.id, {"pilot_email": email, "booking_ref": booking_ref})
    db.commit()
    subject = f"FlySunbird: Assigned to flight (booking {b.booking_ref})"
    email_body = f"Booking {b.booking_ref} is paid. You have been assigned to this flight. Time entry: {b.time_entry_id}."
    queue_email(db, email, subject, email_body, related_booking_ref=b.booking_ref)
    return {"ok": True, "assignmentId": pa.id}


# -------------------------
# CANCELLATIONS
# -------------------------
@router.post("/ops/bookings/{booking_ref}/cancel")
def ops_cancel_booking(
    booking_ref: str,
    body: CancellationDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")

    # Release seats if not already completed/expired
    te = db.get(TimeEntry, b.time_entry_id)
    if te and b.status not in ["EXPIRED","CANCELLED"]:
        te.seats_available += b.pax

    b.status = "CANCELLED"
    if b.payment_status == "paid":
        b.payment_status = "refunded" if body.refund_amount_usd > 0 else "paid"

    c = Cancellation(
        id=str(uuid.uuid4()),
        booking_id=b.id,
        booking_ref=b.booking_ref,
        requested_by_user_id=user.id,
        reason=body.decision_note or "ops_cancel",
        status="approved",
        refund_amount_usd=max(int(body.refund_amount_usd or 0), 0),
        decided_by_user_id=user.id,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(c)
    log_audit(db, user.id, "booking.cancel", "booking", b.id, {"refund": c.refund_amount_usd})
    db.commit()
    return {"ok": True, "bookingRef": b.booking_ref, "status": b.status}

@router.get("/ops/cancellations")
def list_cancellations(
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    q = db.query(Cancellation)
    if status:
        q = q.filter(Cancellation.status == status)
    items = q.order_by(Cancellation.created_at.desc()).limit(500).all()
    return [{
        "id": c.id,
        "bookingRef": c.booking_ref,
        "status": c.status,
        "refundAmountUSD": c.refund_amount_usd,
        "reason": c.reason,
        "createdAt": c.created_at.isoformat(),
        "decidedAt": c.decided_at.isoformat() if c.decided_at else None,
    } for c in items]


# -------------------------
# BOOKING ACTIONS: MOVE / REFUND / RESEND TICKET
# -------------------------
@router.post("/ops/bookings/{booking_ref}/move")
def move_booking(
    booking_ref: str,
    body: MoveBookingIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")

    target = (body.target or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Missing target")

    # Accept either time_entry UUID or "YYYY-MM-DD HH:MM"
    te_id = ""
    if len(target) >= 30 and "-" in target:
        te_id = target
    else:
        # Parse "YYYY-MM-DD HH:MM"
        parts = target.split()
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Target must be Time Entry ID or 'YYYY-MM-DD HH:MM'")
        date_str, start = parts[0].strip(), parts[1].strip()
        q = db.query(TimeEntry).filter(TimeEntry.date_str == date_str, TimeEntry.start == start)
        # Prefer same route as current
        cur = db.get(TimeEntry, b.time_entry_id)
        if cur:
            q = q.filter(TimeEntry.route_id == cur.route_id)
        te = q.first()
        if not te:
            raise HTTPException(status_code=404, detail="Target time entry not found")
        te_id = te.id

    new_te = db.get(TimeEntry, te_id)
    if not new_te:
        raise HTTPException(status_code=404, detail="Target time entry not found")

    old_te = db.get(TimeEntry, b.time_entry_id) if b.time_entry_id else None

    pax = int(b.pax or 1)
    if new_te.seats_available < pax:
        raise HTTPException(status_code=409, detail="Not enough seats in target time entry")

    # Adjust inventory atomically
    try:
        if old_te:
            old_te.seats_available = int(old_te.seats_available or 0) + pax
        new_te.seats_available = int(new_te.seats_available or 0) - pax
        b.time_entry_id = new_te.id
        log_audit(db, user.id, "booking.move", "booking", b.id, {"booking_ref": booking_ref, "target": te_id, "reason": body.reason})
        db.commit()
    except Exception as e:
        db.rollback()
        raise

    return {"ok": True, "bookingRef": booking_ref, "movedTo": new_te.id}

@router.post("/ops/bookings/{booking_ref}/refund")
def refund_booking(
    booking_ref: str,
    body: RefundIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")

    amt = int(body.amount or 0)
    if amt < 0:
        raise HTTPException(status_code=400, detail="Amount must be >= 0")

    p = Payment(id=str(uuid.uuid4()), booking_id=b.id, provider="manual", amount_usd=amt, currency="USD", status="refunded", provider_ref="ops_refund")
    db.add(p)
    b.payment_status = "refunded"
    log_audit(db, user.id, "booking.refund", "booking", b.id, {"booking_ref": booking_ref, "amount_usd": amt, "reason": body.reason})
    db.commit()
    return {"ok": True, "bookingRef": booking_ref, "refunded": amt}

@router.post("/ops/bookings/{booking_ref}/resend-ticket")
def resend_ticket(
    booking_ref: str,
    body: ResendTicketIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    import os
    from app.core.config import settings

    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")

    booker = db.get(User, b.user_id) if b.user_id else None
    if not booker or not booker.email:
        raise HTTPException(status_code=400, detail="Booker email not available")

    subject = f"FlySunbird Ticket • {b.booking_ref}"
    body_txt = f"Your ticket reference is {b.booking_ref}.\n\nStatus: {b.status}\nPayment: {b.payment_status}.\n\nPlease find your ticket PDF attached."
    attachments = []
    if getattr(b, "ticket_storage", None) == "local" and getattr(b, "ticket_object_key", None):
        path = b.ticket_object_key
        if not os.path.isabs(path):
            base = getattr(settings, "TICKET_LOCAL_DIR", None) or "./data/tickets"
            path = os.path.join(base, os.path.basename(path))
        if os.path.isfile(path):
            with open(path, "rb") as f:
                attachments.append((f"{b.booking_ref}.pdf", f.read(), "application/pdf"))
    queue_email(db, booker.email, subject, body_txt, related_booking_ref=b.booking_ref, attachments=attachments or None)
    log_audit(db, user.id, "ticket.resend", "booking", b.id, {"booking_ref": booking_ref, "reason": body.reason})
    db.commit()
    return {"ok": True, "sentTo": booker.email, "attachment": bool(attachments)}


# -------------------------
# OVERVIEW: today's slots/seats from slot rules (by weekday, like booking calendar)
# -------------------------
class OverviewTodayStats(BaseModel):
    dateStr: str
    weekday: int  # 0=Mon .. 6=Sun
    inventorySlots: int
    seatsAvailable: int


@router.get("/ops/dashboard/today-stats", response_model=OverviewTodayStats)
def dashboard_today_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    """Count slots and seats for today from slot rules (same logic as booking calendar: weekday → rules → flights per day, capacity per flight)."""
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()
    weekday = today.weekday()  # 0=Mon .. 6=Sun
    rules = db.query(SlotRule).filter(SlotRule.active == True).all()
    inventory_slots = 0
    seats_available = 0
    for r in rules:
        days = {int(x) for x in (r.days_of_week or "").split(",") if x.strip().isdigit()}
        if weekday not in days:
            continue
        times = [t.strip() for t in (r.times or "").split(",") if t.strip()]
        n = len(times)
        cap = int(r.capacity or 0)
        inventory_slots += n
        seats_available += n * cap
    return OverviewTodayStats(
        dateStr=today_str,
        weekday=weekday,
        inventorySlots=inventory_slots,
        seatsAvailable=seats_available,
    )


# -------------------------
# INVENTORY: TIME ENTRIES
# -------------------------
@router.get("/ops/time-entries", response_model=list[TimeEntryOut])
def list_time_entries(
    route_id: str = "",
    dateStr: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    q = db.query(TimeEntry)
    if route_id:
        q = q.filter(TimeEntry.route_id == route_id)
    if dateStr:
        if dateStr.strip().lower() == "today":
            dateStr = datetime.now(timezone.utc).date().isoformat()
        q = q.filter(TimeEntry.date_str == dateStr)
    items = q.order_by(TimeEntry.date_str.asc(), TimeEntry.start.asc()).limit(2000).all()
    out = []
    for t in items:
        route = db.get(Route, t.route_id) if t.route_id else None
        out.append(TimeEntryOut(**{
            "id": t.id, "route_id": t.route_id, "date_str": t.date_str, "start": t.start, "end": t.end,
            "price_usd": t.price_usd, "price_tzs": getattr(t, "price_tzs", None), "seats_available": t.seats_available,
            "flight_no": t.flight_no, "cabin": t.cabin,
            "base_price_usd": getattr(t, "base_price_usd", 0) or 0, "base_price_tzs": getattr(t, "base_price_tzs", None),
            "override_price_usd": getattr(t, "override_price_usd", None), "override_price_tzs": getattr(t, "override_price_tzs", None),
            "from_label": route.from_label if route else None,
            "to_label": route.to_label if route else None,
        }))
    return out

@router.post("/ops/time-entries", response_model=TimeEntryOut)
def create_time_entry(
    body: TimeEntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    t = TimeEntry(id=str(uuid.uuid4()), **body.model_dump())
    db.add(t)
    log_audit(db, user.id, "time_entry.create", "time_entry", t.id, body.model_dump())
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not create (duplicate?)") from e
    return TimeEntryOut(id=t.id, **body.model_dump())

@router.patch("/ops/time-entries/{time_entry_id}", response_model=TimeEntryOut)
def update_time_entry(
    time_entry_id: str,
    body: TimeEntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    t = db.get(TimeEntry, time_entry_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    # Ensure seats_available is not reduced below already-booked pax
    if body.seats_available is not None:
        booked = db.query(func.coalesce(func.sum(Booking.pax), 0)).filter(
            Booking.time_entry_id == time_entry_id,
            Booking.status.notin_(["EXPIRED", "CANCELLED"]),
        ).scalar() or 0
        if int(body.seats_available) < int(booked):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set seats below already-booked count ({int(booked)}).",
            )
    for k,v in body.model_dump().items():
        setattr(t, k, v)
    log_audit(db, user.id, "time_entry.update", "time_entry", t.id, body.model_dump())
    db.commit()
    return TimeEntryOut(id=t.id, **body.model_dump())

@router.delete("/ops/time-entries/{time_entry_id}")
def delete_time_entry(
    time_entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    t = db.get(TimeEntry, time_entry_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(t)
    log_audit(db, user.id, "time_entry.delete", "time_entry", time_entry_id, {})
    db.commit()
    return {"ok": True}

# -------------------------
# WEEKLY FLEET OPERATIONS PLAN IMPORT
# -------------------------
@router.get("/ops/weekly-plan/presets")
def weekly_plan_presets(user: User = Depends(require_roles("ops", "admin", "superadmin"))):
    """List embedded weekly plan presets (e.g. 5H-FSA). Returns { planId: [ legs ] }."""
    return {pid: [{"day_of_week": l.day_of_week, "from_code": l.from_code, "to_code": l.to_code, "start": l.start, "end": l.end, "duration_minutes": l.duration_minutes} for l in get_preset_legs(pid)] for pid in PRESETS}

@router.post("/ops/weekly-plan/import", response_model=WeeklyPlanImportResponse)
def weekly_plan_import(
    body: WeeklyPlanImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops", "admin", "superadmin")),
):
    """Import a weekly operations plan (e.g. 5H-FSA helicopter). Creates routes if needed and time entries for the given week. Use plan_id='5H-FSA' to use the embedded plan."""
    result = import_weekly_plan(db, body)
    db.commit()
    legs_used = len(body.legs) if body.legs else len(get_preset_legs(body.plan_id or ""))
    log_audit(db, user.id, "weekly_plan.import", "weekly_plan", body.week_start_date, {"legs": legs_used, "created": result.time_entries_created})
    return result

# -------------------------
# INVENTORY: SLOT RULES (GENERATORS)
# -------------------------
@router.get("/ops/slot-rules", response_model=list[SlotRuleOut], operation_id="ops_list_slot_rules")
def list_slot_rules(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    items = db.query(SlotRule).order_by(SlotRule.created_at.desc()).all()
    return [SlotRuleOut(id=r.id, **{
        "route_id": r.route_id, "days_of_week": r.days_of_week, "times": r.times,
        "duration_minutes": r.duration_minutes, "price_usd": r.price_usd, "capacity": r.capacity,
        "flight_no_prefix": r.flight_no_prefix, "cabin": r.cabin, "active": r.active, "horizon_days": r.horizon_days
    }) for r in items]

@router.post("/ops/slot-rules", response_model=SlotRuleOut)
def create_slot_rule(
    body: SlotRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    r = SlotRule(id=str(uuid.uuid4()), **body.model_dump())
    db.add(r)
    log_audit(db, user.id, "slot_rule.create", "slot_rule", r.id, body.model_dump())
    db.commit()
    return SlotRuleOut(id=r.id, **body.model_dump())

@router.patch("/ops/slot-rules/{rule_id}", response_model=SlotRuleOut)
def update_slot_rule(
    rule_id: str,
    body: SlotRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    r = db.get(SlotRule, rule_id)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    for k,v in body.model_dump().items():
        setattr(r, k, v)
    log_audit(db, user.id, "slot_rule.update", "slot_rule", r.id, body.model_dump())
    db.commit()
    return SlotRuleOut(id=r.id, **body.model_dump())

@router.post("/ops/slot-rules/{rule_id}/run-now")
def run_slot_rule_now(
    rule_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin")),
):
    # simply enqueue generator job; for local we can call synchronously by importing
    from app.tasks.worker_jobs import generate_slots
    generate_slots()
    log_audit(db, user.id, "slot_rule.run_now", "slot_rule", rule_id, {})
    return {"ok": True}

# -------------------------
# PAYMENTS (LIST)
# -------------------------

@router.get("/ops/payments")
def list_payments(
    bookingRef: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    q = db.query(Payment, Booking).join(Booking, Booking.id == Payment.booking_id)
    if status:
        q = q.filter(Payment.status == status)
    if bookingRef:
        q = q.filter(Booking.booking_ref == bookingRef)
    rows = q.order_by(Payment.created_at.desc()).limit(2000).all()
    return [{
        "id": p.id,
        "bookingRef": b.booking_ref,
        "provider": p.provider,
        "status": p.status,
        "amountUSD": p.amount_usd,
        "currency": p.currency,
        "providerRef": p.provider_ref,
        "createdAt": p.created_at.isoformat(),
    } for p, b in rows]

# -------------------------
# DASHBOARD METRICS (HISTOGRAM DATA)
# -------------------------
@router.get("/ops/dashboard/metrics", response_model=DashboardMetrics)
def dashboard_metrics(
    days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ops","admin","superadmin","finance")),
):
    days = max(1, min(days, 365))
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days-1)

    # totals
    bookings_total = db.query(func.count(Booking.id)).scalar() or 0
    bookings_paid = db.query(func.count(Booking.id)).filter(Booking.payment_status == "paid").scalar() or 0
    bookings_pending = db.query(func.count(Booking.id)).filter(Booking.status == "PENDING_PAYMENT").scalar() or 0
    cancellations_requested = db.query(func.count(Cancellation.id)).filter(Cancellation.status == "requested").scalar() or 0
    cancellations_approved = db.query(func.count(Cancellation.id)).filter(Cancellation.status == "approved").scalar() or 0

    # revenue & seats sold from paid bookings
    revenue_total = 0
    seats_sold_total = 0
    paid_rows = db.query(Booking.pax, TimeEntry.price_usd).join(TimeEntry, TimeEntry.id == Booking.time_entry_id).filter(Booking.payment_status == "paid").all()
    for pax, price in paid_rows:
        seats_sold_total += int(pax or 0)
        revenue_total += int(pax or 0) * int(price or 0)

    # series bookings_by_day and revenue_by_day based on created_at date
    series_bookings = []
    series_revenue = []
    for i in range(days):
        d = start + timedelta(days=i)
        d0 = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        d1 = d0 + timedelta(days=1)
        bcount = db.query(func.count(Booking.id)).filter(and_(Booking.created_at >= d0, Booking.created_at < d1)).scalar() or 0
        # revenue: paid bookings created that day
        paid_day = db.query(Booking.pax, TimeEntry.price_usd).join(TimeEntry, TimeEntry.id == Booking.time_entry_id).filter(
            and_(Booking.created_at >= d0, Booking.created_at < d1),
            Booking.payment_status == "paid",
        ).all()
        rev = sum(int(p or 0)*int(pr or 0) for p, pr in paid_day)
        series_bookings.append(DashboardSeriesPoint(date=d.isoformat(), value=int(bcount)))
        series_revenue.append(DashboardSeriesPoint(date=d.isoformat(), value=int(rev)))

    return DashboardMetrics(
        bookings_total=int(bookings_total),
        bookings_paid=int(bookings_paid),
        bookings_pending=int(bookings_pending),
        cancellations_requested=int(cancellations_requested),
        cancellations_approved=int(cancellations_approved),
        revenue_usd_total=int(revenue_total),
        seats_sold_total=int(seats_sold_total),
        bookings_by_day=series_bookings,
        revenue_by_day=series_revenue,
    )


# =========================
# Slot Rules (inventory generation)
# =========================
from app.models.slot_rule import SlotRule


# -------------------------
# INVENTORY: ROUTES
# -------------------------
@router.get("/ops/routes")
def ops_list_routes(db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    items = db.query(Route).order_by(Route.created_at.desc()).all()
    return [{"id":r.id,"from":r.from_label,"to":r.to_label,"region":r.region,"mainRegion": getattr(r,"main_region","MAINLAND"), "subRegion": getattr(r,"sub_region",None), "active":getattr(r,"active",True)} for r in items]

@router.post("/ops/routes")
def ops_create_route(fromLabel: str, toLabel: str, region: str = "Tanzania", mainRegion: str = "MAINLAND", subRegion: str | None = None, active: bool = True,
                     db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    r = Route(id=str(uuid.uuid4()), from_label=fromLabel, to_label=toLabel, region=region, main_region=mainRegion, sub_region=subRegion, active=active)
    db.add(r)
    log_audit(db, user.id, "route.create", "route", r.id, {"from":fromLabel,"to":toLabel,"region":region,"mainRegion":mainRegion,"subRegion":subRegion,"active":active})
    db.commit()
    return {"id": r.id}

@router.patch("/ops/routes/{route_id}")
def ops_update_route(route_id: str, fromLabel: str | None = None, toLabel: str | None = None, region: str | None = None, mainRegion: str | None = None, subRegion: str | None = None, active: bool | None = None,
                     db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    r = db.get(Route, route_id)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if fromLabel is not None: r.from_label = fromLabel
    if toLabel is not None: r.to_label = toLabel
    if region is not None: r.region = region
    if mainRegion is not None: setattr(r,"main_region", mainRegion)
    if subRegion is not None: setattr(r,"sub_region", subRegion)
    if active is not None: r.active = active
    log_audit(db, user.id, "route.update", "route", r.id, {"fromLabel":fromLabel,"toLabel":toLabel,"region":region,"mainRegion":mainRegion,"subRegion":subRegion,"active":active})
    db.commit()
    return {"ok": True}

@router.delete("/ops/routes/{route_id}")
def ops_delete_route(route_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    r = db.get(Route, route_id)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    # soft-delete: just deactivate
    r.active = False
    log_audit(db, user.id, "route.deactivate", "route", r.id, {})
    db.commit()
    return {"ok": True}

# -------------------------
# SETTINGS: FX RATE
# -------------------------
from app.services.settings_service import get_usd_to_tzs_rate, set_usd_to_tzs_rate, get_terms, set_terms

@router.get("/ops/settings/payment-status")
def get_payment_status(user: User = Depends(require_roles("ops","admin","superadmin","finance"))):
    """Return whether payment/ticket config is set (no secrets)."""
    from app.core.config import settings
    cybs_ok = bool(
        getattr(settings, "CYBS_MERCHANT_ID", None)
        and getattr(settings, "CYBS_KEY_ID", None)
        and getattr(settings, "CYBS_SECRET_KEY_B64", None)
    )
    client_base = (getattr(settings, "CLIENT_BASE_URL", None) or "").strip()
    api_public = (getattr(settings, "API_PUBLIC_URL", None) or "").strip()
    ticket_dir = getattr(settings, "TICKET_LOCAL_DIR", "") or "./data/tickets"
    return {
        "cybersourceConfigured": cybs_ok,
        "clientBaseUrlSet": bool(client_base),
        "apiPublicUrlSet": bool(api_public),
        "ticketLocalDir": ticket_dir,
        "cybsEnv": getattr(settings, "CYBS_ENV", "test"),
    }

@router.get("/ops/settings/fx-rate")
def get_fx_rate(db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    return {"usdToTzs": get_usd_to_tzs_rate(db)}

@router.post("/ops/settings/fx-rate")
def set_fx_rate(usdToTzs: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "superadmin", "ops"))):
    try:
        rate = set_usd_to_tzs_rate(db, usdToTzs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_audit(db, user.id, "settings.fx_rate", "setting", "USD_TO_TZS", {"usdToTzs": rate})
    return {"usdToTzs": rate}


class TermsIn(BaseModel):
    version: str = "2025"
    docSha256: str = ""
    url: str = "fly/terms-and-conditions.html"


@router.get("/ops/settings/terms")
def get_terms_settings(db: Session = Depends(get_db), user: User = Depends(require_roles("ops", "admin", "superadmin", "finance"))):
    return get_terms(db)


@router.post("/ops/settings/terms")
def post_terms_settings(body: TermsIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ops", "admin", "superadmin"))):
    data = set_terms(db, body.version, body.docSha256, body.url)
    log_audit(db, user.id, "settings.terms", "setting", "TERMS", {"version": body.version})
    return data


# -------------------------
# OPS RESET (DANGEROUS)
# -------------------------
@router.post("/ops/reset/all")
def ops_reset_all(seed: bool = True,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin","superadmin"))):
    # Wipe operational + analytics data, INCLUDING routes + slot rules (per requirement)
    # Order matters due to FKs not declared but still best practice
    for table in ["email_logs", "pilot_assignments", "payments", "passengers", "cancellations", "audit_logs", "bookings", "time_entries", "slot_rules", "routes"]:
        db.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    db.commit()
    if seed:
        from app.seed import run as seed_run
        seed_run()
    return {"ok": True, "seeded": seed}


@router.get("/ops/bookings/{booking_ref}/payment-link")
def ops_get_payment_link(booking_ref: str, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    # This returns a frontend URL where the customer can complete payment (microform).
    # Configure CLIENT_BASE_URL in .env to match where your client is hosted.
    from app.core.config import settings
    client_base = getattr(settings, "CLIENT_BASE_URL", "").rstrip("/")
    if not client_base:
        return {"bookingRef": booking_ref, "url": "", "note": "Set CLIENT_BASE_URL in .env (e.g., https://flysunbird.co.tz) to generate a clickable payment link."}
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    params = {"bookingRef": booking_ref}
    if b:
        amount = getattr(b, "total_usd", None) or (getattr(b, "unit_price_usd", 0) or 0) * (b.pax or 1)
        params["amount"] = amount
        params["currency"] = getattr(b, "currency", "USD") or "USD"
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return {"bookingRef": booking_ref, "url": f"{client_base}/fly/payment.html?{qs}"}


# -------------------------
# LOCATIONS
# -------------------------
@router.get("/ops/locations")
def ops_list_locations(db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    items = db.query(Location).order_by(Location.region.asc(), Location.name.asc()).all()
    return [{"id":l.id,"region":l.region,"code":l.code,"name":l.name,"subs":l.subs,"active":bool(l.active)} for l in items]

@router.post("/ops/locations")
def ops_create_location(body: LocationIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    l = Location(id=str(uuid.uuid4()), region=body.region, code=body.code, name=body.name, subs_csv=",".join(body.subs or []), active=bool(body.active))
    db.add(l); db.commit()
    return {"id": l.id}

@router.patch("/ops/locations/{loc_id}")
def ops_patch_location(loc_id: str, body: LocationPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    l = db.get(Location, loc_id)
    if not l: raise HTTPException(status_code=404, detail="Location not found")
    if body.region is not None: l.region = body.region
    if body.code is not None: l.code = body.code
    if body.name is not None: l.name = body.name
    if body.subs is not None: l.subs_csv = ",".join(body.subs or [])
    if body.active is not None: l.active = bool(body.active)
    db.commit()
    return {"ok": True}

@router.delete("/ops/locations/{loc_id}")
def ops_delete_location(loc_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","admin","superadmin"))):
    l = db.get(Location, loc_id)
    if not l: return {"ok": True}
    db.delete(l); db.commit()
    return {"ok": True}
