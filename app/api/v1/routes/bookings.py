import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.booking import Booking
from app.models.time_entry import TimeEntry
from app.models.route import Route
from app.models.passenger import Passenger
from app.schemas.booking import BookingCreate, BookingOut
from app.core.config import settings
from app.core.security import hash_password
from app.services.booking_service import create_booking

router = APIRouter(tags=["bookings"])

def get_or_create_booker(db: Session, email: str, name: str) -> User:
    u = db.query(User).filter(User.email == email.lower()).first()
    if u:
        return u
    u = User(
        id=str(uuid.uuid4()),
        email=email.lower(),
        full_name=name or "",
        role="customer",
        password_hash=hash_password(str(uuid.uuid4())),  # random; can reset later
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u

@router.post("/public/bookings", response_model=BookingOut)
def create_public_booking(body: BookingCreate, db: Session = Depends(get_db)):
    try:
        booker = get_or_create_booker(db, body.bookerEmail, body.bookerName)
        booking = create_booking(db, body.timeEntryId, booker, body.pax, [p.model_dump() for p in body.passengers])
        return BookingOut(
            bookingRef=booking.booking_ref,
            status=booking.status,
            paymentStatus=booking.payment_status,
            holdExpiresAt=booking.hold_expires_at.isoformat() if booking.hold_expires_at else None,
            unitPriceUSD=getattr(booking,'unit_price_usd',0),
            unitPriceTZS=getattr(booking,'unit_price_tzs',0),
            totalUSD=getattr(booking,'total_usd',0),
            totalTZS=getattr(booking,'total_tzs',0),
            currency=getattr(booking,'currency','USD'),
            exchangeRateUsed=getattr(booking,'exchange_rate_used',None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/public/bookings/{booking_ref}")
def get_booking(booking_ref: str, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    te = db.get(TimeEntry, b.time_entry_id) if b.time_entry_id else None
    route = db.get(Route, te.route_id) if te and getattr(te, "route_id", None) else None
    pax = db.query(Passenger).filter(Passenger.booking_id == b.id).all()
    booker = db.get(User, b.user_id) if b.user_id else None
    out = {
        "bookingRef": b.booking_ref,
        "status": b.status,
        "paymentStatus": b.payment_status,
        "timeEntryId": b.time_entry_id,
        "pax": b.pax,
        "holdExpiresAt": b.hold_expires_at.isoformat() if b.hold_expires_at else None,
        "unitPriceUSD": getattr(b,"unit_price_usd",0),
        "unitPriceTZS": getattr(b,"unit_price_tzs",0),
        "totalUSD": getattr(b,"total_usd",0),
        "totalTZS": getattr(b,"total_tzs",0),
        "currency": getattr(b,"currency","USD"),
        "exchangeRateUsed": getattr(b,"exchange_rate_used",None),
    }
    if te:
        out["from"] = route.from_label if route else None
        out["to"] = route.to_label if route else None
        out["dateStr"] = te.date_str
        out["timeEntry"] = {
            "start": te.start, "end": te.end, "flightNo": te.flight_no,
            "from_label": route.from_label if route else None,
            "to_label": route.to_label if route else None,
            "date_str": te.date_str,
        }
    out["passengers"] = [{"first": getattr(p, "first", ""), "last": getattr(p, "last", ""), "phone": getattr(p, "phone", "")} for p in pax]
    if booker:
        out["contactEmail"] = booker.email
        out["contactName"] = booker.full_name
    return out


@router.get("/public/bookings/{booking_ref}/ticket")
def download_ticket(booking_ref: str, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b.payment_status != "paid":
        raise HTTPException(status_code=409, detail="Ticket is only available after payment")
    if not b.ticket_object_key:
        raise HTTPException(status_code=404, detail="Ticket not generated yet")

    if b.ticket_storage == "local":
        return FileResponse(path=b.ticket_object_key, media_type="application/pdf", filename=f"{booking_ref}.pdf")

    # GCS: optionally return a signed URL if google-cloud-storage is available
    try:
        from google.cloud import storage  # type: ignore
        from datetime import timedelta
    except Exception:
        return {"storage": "gcs", "objectKey": b.ticket_object_key, "note": "Install google-cloud-storage to generate signed URLs."}

    if not settings.GCS_BUCKET_NAME:
        return {"storage": "gcs", "objectKey": b.ticket_object_key}

    client = storage.Client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(b.ticket_object_key)
    url = blob.generate_signed_url(expiration=timedelta(minutes=20), method="GET")
    return {"storage": "gcs", "url": url}
