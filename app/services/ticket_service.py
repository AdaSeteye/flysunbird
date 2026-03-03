from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import qrcode
try:
    from reportlab.lib.pagesizes import A6
except ImportError:
    A6 = (297.64, 419.53)  # A6 105mm x 148mm in points
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.config import settings


def _ticket_url(booking_ref: str) -> str:
    """Public URL for this ticket (scan QR → open same ticket PDF)."""
    base = (getattr(settings, "API_PUBLIC_URL", None) or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:8000"
    return f"{base}/api/v1/public/bookings/{booking_ref}/ticket"


def _make_qr_image_bytes(url: str, box_size: int = 3, border: int = 2) -> bytes:
    """Return PNG bytes for a QR code encoding the given URL."""
    qr = qrcode.QRCode(version=1, box_size=box_size, border=border, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def render_ticket_pdf_bytes(
    *,
    booking_ref: str,
    passenger_name: str,
    route_from: str,
    route_to: str,
    date_str: str,
    start_time: str,
    end_time: str,
    pax: int,
    payment_status: str,
    flight_no: str = "",
) -> bytes:
    """Return an A6 PDF ticket (small, well-formatted) with QR code. Scan QR opens same ticket."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    w, h = A6

    margin = 18
    x_left = margin
    x_right = w - margin
    y = h - margin

    # ----- Brand header -----
    c.setFillColorRGB(0.15, 0.45, 0.75)
    c.rect(0, h - 36, w, 36, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, h - 26, "FlySunbird")
    c.setFont("Helvetica", 9)
    c.drawString(margin, h - 34, "Flight Ticket")
    c.setFillColorRGB(0, 0, 0)
    y = h - 52

    # ----- Ref + Flight (top line) -----
    c.setFont("Helvetica", 9)
    c.drawString(x_left, y, f"Ref: {booking_ref}")
    if flight_no:
        c.drawRightString(x_right, y, f"Flight {flight_no}")
    y -= 14

    # ----- Trip (prominent) -----
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Trip")
    y -= 14
    c.setFont("Helvetica", 11)
    route_str = f"{route_from}  →  {route_to}"
    c.drawString(x_left, y, route_str[:45] + ("..." if len(route_str) > 45 else ""))
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, f"Date: {date_str}")
    c.drawString(x_left + 100, y, f"Time: {start_time} – {end_time}")
    y -= 14
    c.drawString(x_left, y, f"Passengers: {pax}")
    y -= 22

    # ----- Passenger -----
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Passenger")
    y -= 14
    c.setFont("Helvetica", 11)
    c.drawString(x_left, y, (passenger_name or "(Not provided)")[:50])
    y -= 22

    # ----- Status -----
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Status")
    y -= 14
    c.setFont("Helvetica", 10)
    status_str = (payment_status or "unpaid").capitalize()
    c.drawString(x_left, y, f"Payment: {status_str}")
    y -= 28

    # ----- QR code (box, top-right area) -----
    qr_size = 72
    qr_x = x_right - qr_size
    qr_y = y - qr_size
    try:
        ticket_url = _ticket_url(booking_ref)
        qr_png = _make_qr_image_bytes(ticket_url, box_size=2, border=1)
        img = ImageReader(io.BytesIO(qr_png))
        c.drawImage(img, qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        c.setFont("Helvetica", 8)
        c.drawString(qr_x, qr_y + qr_size / 2 - 4, "QR unavailable")
    c.setFont("Helvetica", 8)
    c.drawString(qr_x, qr_y - 6, "Scan to open ticket")

    # ----- Footer -----
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(x_left, 22, "Generated after payment. Scan QR to view or verify this ticket.")
    c.drawString(x_left, 12, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    c.setFillColorRGB(0, 0, 0)

    c.showPage()
    c.save()
    return buf.getvalue()


def store_ticket_pdf(*, booking_ref: str, pdf_bytes: bytes) -> tuple[str, str]:
    """Store ticket and return (storage_backend, object_key)."""
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
    """Load stored ticket PDF bytes for attachment (e.g. email). Returns None if not found or error."""
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
        # local
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
