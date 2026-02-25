from __future__ import annotations

import io
import os
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings


def render_ticket_pdf_bytes(*, booking_ref: str, passenger_name: str, route_from: str, route_to: str,
                            date_str: str, start_time: str, end_time: str, pax: int,
                            payment_status: str, flight_no: str = "") -> bytes:
    """Return an A4 PDF bytes. Pure function."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, h = A4

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, h - 60, "FlySunbird Ticket")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 80, f"Booking Reference: {booking_ref}")
    if flight_no:
        c.drawString(40, h - 96, f"Flight No: {flight_no}")

    # Passenger block
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, h - 130, "Passenger")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 148, passenger_name or "(Not provided)")

    # Trip block
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, h - 185, "Trip")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 203, f"From: {route_from}")
    c.drawString(40, h - 219, f"To:   {route_to}")
    c.drawString(40, h - 235, f"Date: {date_str}")
    c.drawString(40, h - 251, f"Time: {start_time} - {end_time}")
    c.drawString(40, h - 267, f"PAX:  {pax}")

    # Payment
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, h - 305, "Payment")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 323, f"Status: {payment_status}")

    # Footer
    c.setFont("Helvetica", 9)
    c.drawString(40, 40, "This ticket is generated automatically after successful payment.")
    c.drawString(40, 26, f"Generated: {datetime.now(timezone.utc).isoformat()}")

    c.showPage()
    c.save()
    return buf.getvalue()


def store_ticket_pdf(*, booking_ref: str, pdf_bytes: bytes) -> tuple[str, str]:
    """Store ticket and return (storage_backend, object_key)."""
    # Default local
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

    # local
    base = settings.TICKET_LOCAL_DIR or "./data/tickets"
    os.makedirs(base, exist_ok=True)
    object_key = os.path.join(base, f"{booking_ref}.pdf")
    with open(object_key, "wb") as f:
        f.write(pdf_bytes)
    return "local", object_key
