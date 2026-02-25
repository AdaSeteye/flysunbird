from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_roles
from app.models.user import User
from app.models.pilot import PilotAssignment
from app.models.booking import Booking
from app.models.time_entry import TimeEntry
from app.models.route import Route
from app.services.audit_service import log_audit
from app.services.email_service import queue_email

router = APIRouter(tags=["pilot"])

@router.get("/pilot/assignments")
def my_assignments(db: Session = Depends(get_db), me: User = Depends(require_roles("pilot"))):
    assigns = db.query(PilotAssignment).filter(PilotAssignment.pilot_user_id == me.id).order_by(PilotAssignment.created_at.desc()).all()
    items = []
    for a in assigns:
        te = db.get(TimeEntry, a.time_entry_id)
        route = db.get(Route, te.route_id) if te and te.route_id else None
        bookings = db.query(Booking).filter(Booking.time_entry_id == a.time_entry_id).order_by(Booking.created_at.asc()).all()
        items.append({
            "assignmentId": a.id,
            "timeEntryId": a.time_entry_id,
            "status": a.status,
            "createdAt": a.created_at.isoformat(),
            "completedAt": a.completed_at.isoformat() if a.completed_at else None,
            "dateStr": te.date_str if te else None,
            "start": te.start if te else None,
            "end": te.end if te else None,
            "from_label": route.from_label if route else None,
            "to_label": route.to_label if route else None,
            "routeLabel": (f"{route.from_label} → {route.to_label}") if route and route.from_label and route.to_label else None,
            "bookings": [{
                "bookingRef": b.booking_ref,
                "status": b.status,
                "paymentStatus": b.payment_status,
                "pax": b.pax,
            } for b in bookings]
        })
    return {"items": items}

@router.post("/pilot/assignments/{assignment_id}/accept")
def accept_assignment(assignment_id: str, db: Session = Depends(get_db), me: User = Depends(require_roles("pilot"))):
    a = db.get(PilotAssignment, assignment_id)
    if not a or a.pilot_user_id != me.id:
        raise HTTPException(status_code=404, detail="not found")
    a.status = "accepted"
    db.commit()
    log_audit(db, actor_user_id=me.email, action="pilot_assignment_accepted", entity_type="pilot_assignment", entity_id=a.id, details={})
    return {"ok": True}

@router.post("/pilot/bookings/{booking_ref}/complete")
def complete_flight(booking_ref: str, db: Session = Depends(get_db), me: User = Depends(require_roles("pilot"))):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    a = db.query(PilotAssignment).filter(PilotAssignment.time_entry_id == b.time_entry_id, PilotAssignment.pilot_user_id == me.id).first()
    if not a:
        raise HTTPException(status_code=403, detail="not assigned to this flight")

    b.status = "COMPLETED"
    a.status = "completed"
    a.completed_at = datetime.now(timezone.utc)
    db.commit()
    log_audit(db, actor_user_id=me.email, action="flight_completed", entity_type="booking", entity_id=b.booking_ref, details={"assignmentId": a.id})

    # notify ops (to SMTP_FROM as a fallback)
    queue_email(db, "ops@flysunbird.local", f"FlySunbird flight completed: {b.booking_ref}", f"Pilot {me.email} marked booking {b.booking_ref} as COMPLETED.", b.booking_ref)

    return {"ok": True, "bookingRef": b.booking_ref, "status": b.status}
