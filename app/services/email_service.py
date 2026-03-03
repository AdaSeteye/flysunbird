from datetime import datetime, timezone
import smtplib
from email.message import EmailMessage
from sqlalchemy.orm import Session
import uuid
import requests

from app.core.config import settings
from app.models.email_log import EmailLog


def queue_email(
    db: Session,
    to_email: str,
    subject: str,
    body: str,
    related_booking_ref: str = "",
    attachments: list[tuple[str, bytes, str]] | None = None,
    attach_ticket_booking_ref: str | None = None,
) -> str:
    """Queue and attempt immediate send. Body is stored so the worker can retry on failure.

    attachments: list of (filename, content_bytes, mime_type)
    attach_ticket_booking_ref: when set, retries will re-load and attach the ticket PDF for this booking.
    """
    eid = str(uuid.uuid4())
    db.add(
        EmailLog(
            id=eid,
            to_email=to_email,
            subject=subject,
            body=body,
            status="queued",
            related_booking_ref=related_booking_ref,
            attach_ticket_booking_ref=attach_ticket_booking_ref or None,
        )
    )
    db.commit()

    try:
        send_email(to_email, subject, body, attachments=attachments or [])
        log = db.get(EmailLog, eid)
        if log:
            log.status = "sent"
            log.sent_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        log = db.get(EmailLog, eid)
        if log:
            log.status = "failed"
            db.commit()
        # Worker will retry via process_email_queue

    return eid


def send_email(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]]):
    """Send email via SendGrid if configured, otherwise SMTP (MailHog recommended for local)."""

    if settings.SENDGRID_API_KEY:
        _send_via_sendgrid(to_email, subject, body, attachments)
        return

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    for filename, content, mime in attachments:
        maintype, subtype = (mime.split("/", 1) + ["octet-stream"])[:2]
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


def _send_via_sendgrid(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]]):
    from_email = settings.SENDGRID_FROM_EMAIL or settings.SMTP_FROM
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    if attachments:
        import base64

        payload["attachments"] = [
            {
                "content": base64.b64encode(content).decode("utf-8"),
                "type": mime,
                "filename": filename,
                "disposition": "attachment",
            }
            for filename, content, mime in attachments
        ]

    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"SendGrid error {r.status_code}: {r.text}")


def process_pending_emails(db: Session, limit: int = 50) -> dict:
    """Process up to `limit` queued or failed emails; retry send and update status. Returns counts.
    When attach_ticket_booking_ref is set, loads ticket PDF and attaches it on retry."""
    from app.models.booking import Booking
    from app.services.ticket_service import load_ticket_pdf_bytes

    pending = (
        db.query(EmailLog)
        .filter(EmailLog.status.in_(["queued", "failed"]), EmailLog.body.isnot(None), EmailLog.body != "")
        .order_by(EmailLog.created_at.asc())
        .limit(limit)
        .all()
    )
    sent, failed = 0, 0
    for log in pending:
        attachments: list[tuple[str, bytes, str]] = []
        if getattr(log, "attach_ticket_booking_ref", None):
            ref = (log.attach_ticket_booking_ref or "").strip()
            if ref:
                b = db.query(Booking).filter(Booking.booking_ref == ref).first()
                if b and getattr(b, "ticket_object_key", None):
                    pdf = load_ticket_pdf_bytes(
                        booking_ref=ref,
                        storage=getattr(b, "ticket_storage", None) or "local",
                        object_key=b.ticket_object_key,
                    )
                    if pdf:
                        attachments.append((f"{ref}.pdf", pdf, "application/pdf"))
        try:
            send_email(log.to_email, log.subject, log.body, attachments)
            log.status = "sent"
            log.sent_at = datetime.now(timezone.utc)
            sent += 1
        except Exception:
            log.status = "failed"
            failed += 1
    if pending:
        db.commit()
    return {"processed": len(pending), "sent": sent, "failed": failed}


def send_booking_confirmation_and_ticket(db: Session, booking_ref: str) -> bool:
    """Send confirmation + ticket PDF to the booker when payment is confirmed. Returns True if sent."""
    from app.models.booking import Booking
    from app.models.user import User
    from app.services.ticket_service import load_ticket_pdf_bytes

    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b or not getattr(b, "ticket_object_key", None):
        return False
    booker = db.get(User, b.user_id) if b.user_id else None
    if not booker or not (getattr(booker, "email", None) or "").strip():
        return False
    to_email = booker.email.strip()
    subject = f"FlySunbird Booking Confirmed • {b.booking_ref}"
    body = (
        f"Your payment has been confirmed. Booking reference: {b.booking_ref}.\n\n"
        f"Status: {b.status}\nPayment: {b.payment_status}.\n\n"
        f"Your ticket is attached. You can also view or download it from the booking link."
    )
    attachments: list[tuple[str, bytes, str]] = []
    pdf = load_ticket_pdf_bytes(
        booking_ref=b.booking_ref,
        storage=getattr(b, "ticket_storage", None) or "local",
        object_key=b.ticket_object_key,
    )
    if pdf:
        attachments.append((f"{b.booking_ref}.pdf", pdf, "application/pdf"))
    queue_email(
        db,
        to_email,
        subject,
        body,
        related_booking_ref=b.booking_ref,
        attachments=attachments or None,
        attach_ticket_booking_ref=b.booking_ref,
    )
    return True
