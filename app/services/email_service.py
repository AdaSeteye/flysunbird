from datetime import datetime, timezone
import smtplib
from email.message import EmailMessage
from sqlalchemy.orm import Session
import uuid
import requests

from app.core.config import settings
from app.models.email_log import EmailLog


def queue_email(db: Session, to_email: str, subject: str, body: str, related_booking_ref: str = "", attachments: list[tuple[str, bytes, str]] | None = None) -> str:
    """Queue and attempt immediate send. Body is stored so the worker can retry on failure.

    attachments: list of (filename, content_bytes, mime_type)
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
    """Process up to `limit` queued or failed emails; retry send and update status. Returns counts."""
    pending = (
        db.query(EmailLog)
        .filter(EmailLog.status.in_(["queued", "failed"]), EmailLog.body.isnot(None), EmailLog.body != "")
        .order_by(EmailLog.created_at.asc())
        .limit(limit)
        .all()
    )
    sent, failed = 0, 0
    for log in pending:
        try:
            send_email(log.to_email, log.subject, log.body, [])
            log.status = "sent"
            log.sent_at = datetime.now(timezone.utc)
            sent += 1
        except Exception:
            log.status = "failed"
            failed += 1
    if pending:
        db.commit()
    return {"processed": len(pending), "sent": sent, "failed": failed}
