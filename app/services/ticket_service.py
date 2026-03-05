from __future__ import annotations

import io
import os
import re
from datetime import datetime, timezone

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.models.time_entry import TimeEntry
from app.models.route import Route
from app.models.passenger import Passenger
from app.models.user import User


# Check-in & notes text (exact as per reference PDF)
CHECKIN_NOTES = """• A valid government-issued photo ID is required at check-in, and passengers must arrive 30 minutes before departure.
• Children under 16 must travel with an accompanying adult; passengers aged 2+ require their own seat.
• Passenger weight limits apply and must be accurately disclosed during booking.
• Baggage allowance is 10 kg per passenger (soft bags preferred).
• Flights are subject to weather, air traffic, and operational conditions; the pilot's decision is final.
• Intoxicated or disruptive passengers may be denied boarding; medical conditions must be declared in advance.
• For booking changes, contact support within 24 hours of your booking."""


def _ticket_url(booking_ref: str) -> str:
    base = (getattr(settings, "API_PUBLIC_URL", None) or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:8000"
    return f"{base}/api/v1/public/bookings/{booking_ref}/ticket"


def _make_qr_image_bytes(url: str, box_size: int = 3, border: int = 2) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=box_size, border=border, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _duration_minutes(start: str, end: str) -> int:
    """Parse HH:MM start/end and return duration in minutes."""
    def to_mins(s: str) -> int:
        s = (s or "").strip()
        m = re.match(r"(\d{1,2}):(\d{2})", s)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        return 0
    return max(0, to_mins(end) - to_mins(start))


def _format_time_12h(hhmm: str) -> str:
    """Format HH:MM as 11:00 AM."""
    s = (hhmm or "").strip()
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    if not m:
        return s or "—"
    h, mi = int(m.group(1)), int(m.group(2))
    if h == 0:
        return f"12:{mi:02d} AM"
    if h < 12:
        return f"{h}:{mi:02d} AM"
    if h == 12:
        return f"12:{mi:02d} PM"
    return f"{h - 12}:{mi:02d} PM"


def build_ticket_context(db: Session, b: Booking) -> dict | None:
    """Build ticket context from booking for PDF render. Returns dict for render_ticket_pdf_bytes or None."""
    te = db.get(TimeEntry, b.time_entry_id)
    if not te:
        return None
    route = db.get(Route, te.route_id) if te.route_id else None
    route_from = route.from_label if route else "—"
    route_to = route.to_label if route else "—"
    first_passenger = db.query(Passenger).filter(Passenger.booking_id == b.id).order_by(Passenger.created_at.asc()).first()
    passenger_name = f"{(first_passenger.first or '').strip()} {(first_passenger.last or '').strip()}".strip() if first_passenger else ""
    passenger_phone = (first_passenger.phone or "").strip() if first_passenger else ""
    booker = db.get(User, b.user_id) if b.user_id else None
    booker_email = (booker.email or "").strip() if booker else ""
    duration_min = _duration_minutes(te.start or "", te.end or "")
    experience = f"{duration_min} Minutes {(te.cabin or 'Helicopter Scenic').strip()}."
    aircraft_type = (getattr(te, "aircraft_type", None) or "").strip()
    departure_location = (getattr(te, "departure_location", None) or "").strip() or route_from
    amount_usd = int(getattr(b, "total_usd", 0) or 0)
    amount_tzs = int(getattr(b, "total_tzs", 0) or 0)
    currency = (getattr(b, "currency", None) or "USD").strip()
    return {
        "booking_ref": b.booking_ref,
        "passenger_name": passenger_name or "(Not provided)",
        "passenger_phone": passenger_phone,
        "booker_email": booker_email,
        "route_from": route_from,
        "route_to": route_to,
        "date_str": te.date_str or "",
        "start_time": te.start or "",
        "end_time": te.end or "",
        "pax": int(b.pax),
        "payment_status": b.payment_status or "unpaid",
        "flight_no": (te.flight_no or "").strip(),
        "experience": experience,
        "aircraft_type": aircraft_type,
        "departure_location": departure_location,
        "amount_usd": amount_usd,
        "amount_tzs": amount_tzs,
        "currency": currency,
    }


def render_ticket_pdf_bytes(
    *,
    booking_ref: str,
    passenger_name: str,
    passenger_phone: str = "",
    booker_email: str = "",
    route_from: str,
    route_to: str,
    date_str: str,
    start_time: str,
    end_time: str,
    pax: int,
    payment_status: str,
    flight_no: str = "",
    experience: str = "",
    aircraft_type: str = "",
    departure_location: str = "",
    amount_usd: int = 0,
    amount_tzs: int = 0,
    currency: str = "USD",
) -> bytes:
    """Render ticket PDF matching reference layout. Paid: status PAID • CONFIRMED, no bank. Unpaid: UNPAID + BANK INFORMATION."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    margin = 40
    x_left = margin
    x_right = w - margin
    y = h - margin

    is_paid = (payment_status or "").lower() == "paid"
    status_header = "PAID • CONFIRMED" if is_paid else "UNPAID"
    status_line2 = "PAID" if is_paid else "UNPAID"

    # ----- Status header -----
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_left, y, status_header)
    y -= 28

    # ----- BOOKING SUMMARY -----
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_left, y, "BOOKING SUMMARY")
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, f"Booking Ref: {booking_ref}")
    c.drawString(x_right - 80, y, f"Status: {status_line2}")
    y -= 18

    c.drawString(x_left, y, "Passenger")
    y -= 14
    c.drawString(x_left, y, f"Name: {passenger_name or '(Not provided)'}")
    y -= 14
    contact = [s for s in [passenger_phone, booker_email] if s]
    c.drawString(x_left, y, f"Phone/Email: {' / '.join(contact) if contact else '—'}")
    y -= 22

    c.drawString(x_left, y, f"Flight Route: {route_from} → {route_to}")
    y -= 14
    if experience:
        c.drawString(x_left, y, f"Experience: {experience}")
        y -= 14
    c.drawString(x_left, y, f"Date: {date_str}")
    c.drawString(x_left + 200, y, f"Departure Time: {_format_time_12h(start_time)}")
    y -= 14
    if aircraft_type:
        c.drawString(x_left, y, f"Aircraft Type: {aircraft_type}")
        y -= 14
    if departure_location:
        c.drawString(x_left, y, f"Departure Location: {departure_location}")
        y -= 14
    c.drawString(x_left, y, f"Pax: {pax} Seats")
    if amount_usd and amount_tzs:
        c.drawString(x_left + 180, y, f"Amount (USD/TZS): {amount_usd} / {amount_tzs}")
    elif amount_tzs:
        c.drawString(x_left + 180, y, f"Amount (TZS): {amount_tzs}")
    else:
        c.drawString(x_left + 180, y, f"Amount (USD): {amount_usd or 0}")
    y -= 24

    # ----- BANK INFORMATION (unpaid only) -----
    if not is_paid:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_left, y, "BANK INFORMATION")
        y -= 16
        c.setFont("Helvetica", 10)
        bank_name = getattr(settings, "BANK_NAME", "") or "CRDB BANK"
        bank_acc = getattr(settings, "BANK_ACCOUNT_NAME", "") or "PREMIER AIR LIMITED"
        bank_usd = getattr(settings, "BANK_ACCOUNT_USD", "") or "0250000WKYA00"
        bank_tzs = getattr(settings, "BANK_ACCOUNT_TZS", "") or "0150000WKYA00"
        bank_branch = getattr(settings, "BANK_BRANCH", "") or "Palm Beach, Dar es Salaam, Tanzania"
        bank_swift = getattr(settings, "BANK_SWIFT", "") or "CORUTZTZXXX"
        c.drawString(x_left, y, f"• Bank Name: {bank_name}")
        y -= 14
        c.drawString(x_left, y, f"• Account Name (ACC NAME): {bank_acc}")
        y -= 14
        c.drawString(x_left, y, "• Account Numbers")
        y -= 14
        c.drawString(x_left, y, f"• USD - {bank_usd}")
        y -= 14
        c.drawString(x_left, y, f"• TZS - {bank_tzs}")
        y -= 14
        c.drawString(x_left, y, f"• Branch Name: {bank_branch}")
        y -= 14
        c.drawString(x_left, y, f"• SWIFT Code: {bank_swift}")
        y -= 24

    # ----- Check-in & notes -----
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Check-in & notes")
    y -= 16
    c.setFont("Helvetica", 9)
    for line in CHECKIN_NOTES.split("\n"):
        if line.strip():
            c.drawString(x_left, y, line.strip()[:90])
            y -= 12
    y -= 16

    # ----- Scan for details + QR -----
    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, "Scan for details")
    y -= 10
    try:
        ticket_url = _ticket_url(booking_ref)
        qr_png = _make_qr_image_bytes(ticket_url, box_size=2, border=1)
        img = ImageReader(io.BytesIO(qr_png))
        qr_size = 80
        qr_x = x_right - qr_size
        qr_y = y - qr_size
        c.drawImage(img, qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        pass
    y -= 20

    # ----- Footer line -----
    exp_short = (experience or "").split(".")[0].strip() or "Scenic"
    footer = f"{booking_ref} • {passenger_name or 'Passenger'} • {date_str} • {start_time}"
    c.setFont("Helvetica", 8)
    c.drawString(x_left, y, footer[:95])
    y -= 10
    c.drawString(x_left, y, f"{route_from} → {route_to} • Seats: {pax} • {exp_short}")
    y -= 14

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(x_left, 24, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    c.setFillColorRGB(0, 0, 0)

    c.showPage()
    c.save()
    return buf.getvalue()


def store_ticket_pdf(*, booking_ref: str, pdf_bytes: bytes) -> tuple[str, str]:
    if settings.GCS_BUCKET_NAME and settings.GOOGLE_APPLICATION_CREDENTIALS:
        try:
            from google.cloud import storage  # type: ignore
        except Exception as e:
            raise RuntimeError("google-cloud-storage is not installed. Install requirements and retry") from e
        client = storage.Client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        object_key = f"tickets/{booking_ref}.pdf"
        blob = bucket.blob(object_key)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")
        return "gcs", object_key
    base = settings.TICKET_LOCAL_DIR or "./data/tickets"
    os.makedirs(base, exist_ok=True)
    object_key = os.path.join(base, f"{booking_ref}.pdf")
    with open(object_key, "wb") as f:
        f.write(pdf_bytes)
    return "local", object_key


def load_ticket_pdf_bytes(*, booking_ref: str, storage: str, object_key: str) -> bytes | None:
    if not object_key:
        return None
    try:
        if storage == "gcs":
            if not getattr(settings, "GCS_BUCKET_NAME", None):
                return None
            try:
                from google.cloud import storage  # type: ignore
            except Exception:
                return None
            client = storage.Client()
            bucket = client.bucket(settings.GCS_BUCKET_NAME)
            blob = bucket.blob(object_key)
            return blob.download_as_bytes()
        path = object_key
        if not os.path.isabs(path):
            base = getattr(settings, "TICKET_LOCAL_DIR", None) or "./data/tickets"
            path = os.path.join(base, os.path.basename(path))
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None
