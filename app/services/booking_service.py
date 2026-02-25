import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import User
from app.models.booking import Booking
from app.models.passenger import Passenger
from app.models.time_entry import TimeEntry
from app.services.settings_service import get_usd_to_tzs_rate

HOLD_MINUTES = 15

def make_booking_ref() -> str:
    import random, string
    return "FSB-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def create_booking(db: Session, time_entry_id: str, booker: User, pax: int, passengers: list[dict]) -> Booking:
    if pax < 1:
        raise ValueError("pax must be >= 1")

    # Transactional lock to prevent oversell
    te = db.execute(
        select(TimeEntry).where(TimeEntry.id == time_entry_id).with_for_update()
    ).scalar_one_or_none()
    if not te:
        raise ValueError("time entry not found")

    if te.seats_available < pax:
        raise ValueError("not enough seats")

    te.seats_available -= pax
    hold_exp = datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES)

    rate = get_usd_to_tzs_rate(db)
    # Effective pricing (supports base/override)
    unit_usd = int((getattr(te,'override_price_usd',None) or 0) or (getattr(te,'base_price_usd',0) or 0) or int(te.price_usd))
    unit_tzs = int((getattr(te,'override_price_tzs',None) or 0) or (getattr(te,'base_price_tzs',None) or 0) or (int(te.price_tzs) if te.price_tzs is not None else unit_usd * rate))
    total_usd = int(unit_usd * pax)
    total_tzs = int(unit_tzs * pax)

    # booking_ref must be unique
    for _ in range(10):
        ref = make_booking_ref()
        exists = db.query(Booking).filter(Booking.booking_ref == ref).first()
        if not exists:
            break
    else:
        raise ValueError("could not allocate booking reference")

    booking = Booking(
        id=str(uuid.uuid4()),
        booking_ref=ref,
        time_entry_id=time_entry_id,
        user_id=booker.id,
        pax=pax,
        status="PENDING_PAYMENT",
        payment_status="pending",
        hold_expires_at=hold_exp,
        unit_price_usd=unit_usd,
        unit_price_tzs=unit_tzs,
        total_usd=total_usd,
        total_tzs=total_tzs,
        currency=getattr(te,'currency','USD') or 'USD',
        exchange_rate_used=getattr(te,'exchange_rate',None),
    )
    db.add(booking)

    # Payment record is created when Stripe checkout succeeds (webhook) or mark-paid; no duplicate pending row here.

    for p in passengers[:pax]:
        db.add(Passenger(
            id=str(uuid.uuid4()),
            booking_id=booking.id,
            first=p.get("first",""),
            last=p.get("last",""),
            phone=p.get("phone","") or "",
            gender=p.get("gender","") or "",
            dob=p.get("dob","") or "",
            nationality=p.get("nationality","") or "",
            id_type=p.get("idType","") or "",
            id_number=p.get("idNumber","") or "",
        ))

    db.commit()
    db.refresh(booking)
    return booking
