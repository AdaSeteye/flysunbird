from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from app.db.session import get_db
from app.api.deps import require_roles
from app.core.config import settings


def _verify_cybs_webhook(headers: dict, body: bytes, method: str, path: str) -> bool:
    """Verify Cybersource webhook signature (HTTP Signature).

    Enable with CYBS_WEBHOOK_VERIFY=true. This validates:
    - Digest: SHA-256(body)
    - Signature: HMAC-SHA256 over the signing string

    Notes:
    - Cybersource typically includes (request-target), host, date, digest, v-c-merchant-id in the signed headers.
    - If any required header is missing, returns False.
    """
    import base64, hashlib, hmac, re

    signature_header = headers.get("signature") or headers.get("Signature")
    digest_header = headers.get("digest") or headers.get("Digest")
    if not signature_header or not digest_header:
        return False

    m = re.match(r"SHA-256=(.+)", digest_header.strip())
    if not m:
        return False
    expected_digest = base64.b64decode(m.group(1))
    actual_digest = hashlib.sha256(body).digest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        return False

    parts = {}
    for chunk in signature_header.split(","):
        if "=" in chunk:
            k, v = chunk.strip().split("=", 1)
            parts[k] = v.strip().strip('"')
    signed_headers = (parts.get("headers") or "").split()
    received_sig_b64 = parts.get("signature")
    if not signed_headers or not received_sig_b64:
        return False

    signing_lines = []
    for hname in signed_headers:
        hl = hname.lower()
        if hl == "(request-target)":
            signing_lines.append(f"(request-target): {method.lower()} {path}")
        else:
            val = headers.get(hl) or headers.get(hname)
            if val is None:
                return False
            signing_lines.append(f"{hl}: {str(val).strip()}")
    signing_string = "\n".join(signing_lines)

    secret_b64 = settings.CYBS_SECRET_KEY_B64 or ""
    if not secret_b64:
        return False
    secret = base64.b64decode(secret_b64)
    computed = hmac.new(secret, signing_string.encode("utf-8"), hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("ascii")

    return hmac.compare_digest(computed_b64, received_sig_b64)


from app.models.booking import Booking
from app.models.payment import Payment
from app.models.time_entry import TimeEntry
from app.models.route import Route
from app.models.passenger import Passenger
from app.models.user import User
from app.models.pilot import PilotAssignment
from app.services.audit_service import log_audit
from app.services.email_service import queue_email
from app.services.ticket_service import render_ticket_pdf_bytes, store_ticket_pdf
from app.services.cybersource_client import CybersourceClient, CybersourceConfig, CybersourceError
from app.services.settings_service import get_usd_to_tzs_rate
from app.schemas.payments import CybersourceSaleRequest, CybersourceRefundRequest, CybersourceTransientTokenRequest, CaptureContextRequest, BillTo, CardIn

router = APIRouter(tags=["payments"])


def _confirm_booking_paid_from_webhook(db: Session, booking_ref: str, provider_ref: str, status: str, details: dict):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        return
    # idempotent
    if b.payment_status == "paid" and b.status == "CONFIRMED":
        return
    b.payment_status = "paid"
    b.status = "CONFIRMED"
    # update latest payment record
    p = db.query(Payment).filter(Payment.booking_id == b.id, Payment.provider == "cybersource").order_by(Payment.created_at.desc()).first()
    if not p:
        p = Payment(id=str(uuid.uuid4()), booking_id=b.id, provider="cybersource",
                    amount_usd=getattr(b,"total_usd",0), amount_tzs=getattr(b,"total_tzs",0),
                    currency=getattr(b,"currency","USD"), status="paid", provider_ref=provider_ref)
        db.add(p)
    else:
        p.status = "paid"
        p.provider_ref = provider_ref or p.provider_ref

    log_audit(db, actor_user_id="cybersource", action="payment_paid_webhook", entity_type="booking", entity_id=b.booking_ref, details={"status": status, **details})
    _notify_pilot_if_assigned(db, b)
    _generate_ticket_for_booking(db, b)
    db.commit()


def _cybs_client() -> CybersourceClient:
    host = settings.CYBS_HOST or ("apitest.cybersource.com" if settings.CYBS_ENV.lower() == "test" else "api.cybersource.com")
    if not (settings.CYBS_MERCHANT_ID and settings.CYBS_KEY_ID and settings.CYBS_SECRET_KEY_B64):
        raise HTTPException(status_code=500, detail="Cybersource is not configured (missing env vars)")
    return CybersourceClient(CybersourceConfig(
        host=host,
        merchant_id=settings.CYBS_MERCHANT_ID,
        key_id=settings.CYBS_KEY_ID,
        secret_key_b64=settings.CYBS_SECRET_KEY_B64,
    ))

def _booking_amount_usd(db: Session, b: Booking) -> int:
    """Use booking's stored total (agreed at create time); fallback to te.price_usd * pax if missing."""
    total = getattr(b, "total_usd", None)
    if total is not None and int(total) > 0:
        return int(total)
    unit = getattr(b, "unit_price_usd", None)
    if unit is not None and int(unit) > 0:
        return int(unit) * int(b.pax or 1)
    te = db.get(TimeEntry, b.time_entry_id)
    if not te:
        raise HTTPException(status_code=400, detail="Time entry missing")
    return int(te.price_usd) * int(b.pax)

def _ensure_hold_valid(b: Booking):
    if b.hold_expires_at and b.hold_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Booking hold expired. Please re-book.")

def _notify_pilot_if_assigned(db: Session, b: Booking) -> None:
    pa = db.query(PilotAssignment).filter(PilotAssignment.time_entry_id == b.time_entry_id).first()
    if not pa:
        return
    pilot = db.get(User, pa.pilot_user_id)
    if not pilot:
        return
    subject = f"FlySunbird: PAID booking {b.booking_ref} (action required)"
    body = (
        f"Booking {b.booking_ref} is PAID and CONFIRMED.\n\n"
        f"Time Entry: {b.time_entry_id}\n"
        f"PAX: {b.pax}\n"
        f"Please log in and confirm you completed the flight after it happens.\n"
    )
    queue_email(db, pilot.email, subject, body, related_booking_ref=b.booking_ref)



def _generate_ticket_for_booking(db: Session, b: Booking) -> None:
    """Generate and store A4 PDF ticket, update booking fields. Idempotent."""
    if b.ticket_status == "generated" and b.ticket_object_key:
        return
    te = db.get(TimeEntry, b.time_entry_id)
    if not te:
        return
    route = db.get(Route, te.route_id) if te.route_id else None
    route_from = route.from_label if route else "—"
    route_to = route.to_label if route else "—"
    first_passenger = db.query(Passenger).filter(Passenger.booking_id == b.id).order_by(Passenger.created_at.asc()).first()
    passenger_name = f"{(first_passenger.first or '').strip()} {(first_passenger.last or '').strip()}".strip() if first_passenger else ""

    pdf_bytes = render_ticket_pdf_bytes(
        booking_ref=b.booking_ref,
        passenger_name=passenger_name or "(Not provided)",
        route_from=route_from,
        route_to=route_to,
        date_str=te.date_str,
        start_time=te.start,
        end_time=te.end,
        pax=int(b.pax),
        payment_status=b.payment_status,
        flight_no=te.flight_no or "",
    )
    storage, object_key = store_ticket_pdf(booking_ref=b.booking_ref, pdf_bytes=pdf_bytes)
    b.ticket_storage = storage
    b.ticket_object_key = object_key
    b.ticket_status = "generated"
    db.commit()
    return


def _do_cybersource_sale(db: Session, req: CybersourceSaleRequest) -> dict:
    """Shared logic for sale and charge endpoints. Returns response dict."""
    b = db.query(Booking).filter(Booking.booking_ref == req.bookingRef).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_hold_valid(b)
    if b.payment_status == "paid":
        return {"ok": True, "bookingRef": b.booking_ref, "paymentStatus": "paid"}

    amount_usd = _booking_amount_usd(db, b)
    client_ref = b.booking_ref
    currency = (req.currency or "USD").strip().upper()
    if currency == "TZS":
        total_tzs = getattr(b, "total_tzs", None)
        if total_tzs is not None and int(total_tzs) > 0:
            amount_to_charge = int(total_tzs)
        else:
            amount_to_charge = amount_usd * get_usd_to_tzs_rate(db)
    else:
        amount_to_charge = amount_usd
        currency = "USD"

    # Cybersource: USD with 2 decimals, others as integer string
    amount_str = f"{amount_to_charge:.2f}" if currency == "USD" else str(int(amount_to_charge))

    if getattr(settings, "CYBS_SANDBOX", False):
        # Sandbox: skip real Cybersource call so you can test full flow when gateway returns 404 or isn't configured
        resp = {"id": f"sandbox-{client_ref}", "status": "AUTHORIZED"}
        log_audit(db, actor_user_id="public", action="payment_paid", entity_type="booking", entity_id=b.booking_ref, details={"cybs": {"sandbox": True, "id": resp["id"]}})
    else:
        try:
            cybs = _cybs_client()
            resp = cybs.sale_card(
                client_ref=client_ref,
                amount=amount_str,
                currency=currency,
                bill_to=req.billTo.model_dump(),
                card=req.card.model_dump(exclude_none=True),
            )
        except CybersourceError as e:
            err_msg = str(e)
            log_audit(db, actor_user_id="public", action="payment_failed", entity_type="booking", entity_id=b.booking_ref, details={"error": err_msg})
            raise HTTPException(status_code=502, detail=err_msg)

    cybs_id = str(resp.get("id") or "")
    status = str(resp.get("status") or "").upper()

    amount_tzs = int(amount_to_charge) if currency == "TZS" else 0
    p = Payment(
        id=str(uuid.uuid4()),
        booking_id=b.id,
        provider="cybersource",
        amount_usd=amount_usd,
        amount_tzs=amount_tzs,
        currency=currency,
        status="paid" if status not in ("DECLINED","REJECTED","FAILED") else "failed",
        provider_ref=cybs_id or client_ref,
    )
    db.add(p)

    if p.status == "paid":
        b.payment_status = "paid"
        b.status = "CONFIRMED"
        log_audit(db, actor_user_id="public", action="payment_paid", entity_type="booking", entity_id=b.booking_ref, details={"cybs": {"id": cybs_id, "status": status}})
        _notify_pilot_if_assigned(db, b)
        _generate_ticket_for_booking(db, b)
        # Update booker email from billing if it was a placeholder (customer entered real email on payment page)
        bill_email = (req.billTo.email or "").strip().lower()
        if bill_email and b.user_id:
            booker = db.get(User, b.user_id)
            if booker and (booker.email or "").lower() in ("customer@flysunbird.local", ""):
                booker.email = bill_email
    else:
        b.payment_status = "failed"
        b.status = "PAYMENT_FAILED"
        log_audit(db, actor_user_id="public", action="payment_declined", entity_type="booking", entity_id=b.booking_ref, details={"cybs": {"id": cybs_id, "status": status}})

    db.commit()
    return {
        "ok": p.status == "paid",
        "bookingRef": b.booking_ref,
        "paymentStatus": b.payment_status,
        "cybersource": {"id": cybs_id, "status": status},
    }


@router.post("/public/payments/cybersource/sale")
def cybersource_sale(req: CybersourceSaleRequest, db: Session = Depends(get_db)):
    return _do_cybersource_sale(db, req)


@router.post("/public/payments/cybersource/charge")
def cybersource_charge(body: dict, db: Session = Depends(get_db)):
    """Accept frontend Cybersource-style payload (clientReferenceInformation, orderInformation, paymentInformation) and map to sale.
    PCI: For production, prefer Microform + POST /public/payments/cybersource/transient-token so card data never touches this server."""
    cri = body.get("clientReferenceInformation") or {}
    booking_ref = cri.get("code") or body.get("bookingRef")
    if not booking_ref:
        raise HTTPException(status_code=400, detail="Missing bookingRef (clientReferenceInformation.code)")

    oi = body.get("orderInformation") or {}
    amt = oi.get("amountDetails") or {}
    currency = (amt.get("currency") or "USD").upper()

    bill_to_raw = oi.get("billTo") or {}
    bill_to = BillTo(
        firstName=bill_to_raw.get("firstName", ""),
        lastName=bill_to_raw.get("lastName", ""),
        address1=bill_to_raw.get("address1", ""),
        address2=bill_to_raw.get("address2", ""),
        locality=bill_to_raw.get("locality", ""),
        administrativeArea=bill_to_raw.get("administrativeArea", ""),
        postalCode=bill_to_raw.get("postalCode", ""),
        country=bill_to_raw.get("country", "TZ"),
        email=bill_to_raw.get("email", ""),
        phoneNumber=bill_to_raw.get("phoneNumber", ""),
    )

    pi = body.get("paymentInformation") or {}
    card_raw = pi.get("card") or {}
    card_number = (card_raw.get("number") or "").replace(" ", "").strip()
    if not card_number or len(card_number) < 13:
        raise HTTPException(status_code=400, detail="Valid card number is required (13–19 digits).")
    card = CardIn(
        number=card_number,
        expirationMonth=str(card_raw.get("expirationMonth", "")).strip(),
        expirationYear=str(card_raw.get("expirationYear", "")).strip(),
        securityCode=card_raw.get("securityCode"),
        type=card_raw.get("type"),
    )
    req = CybersourceSaleRequest(bookingRef=booking_ref, billTo=bill_to, card=card, currency=currency)
    return _do_cybersource_sale(db, req)

@router.post("/ops/payments/cybersource/refund")
def cybersource_refund(body: CybersourceRefundRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("ops","finance","admin","superadmin"))):
    b = db.query(Booking).filter(Booking.booking_ref == body.bookingRef).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b.payment_status != "paid":
        raise HTTPException(status_code=409, detail="Booking is not paid")

    payment = db.query(Payment).filter(
        Payment.booking_id == b.id,
        Payment.provider == "cybersource",
        Payment.status == "paid",
    ).order_by(Payment.created_at.desc()).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Cybersource payment not found")

    # Use amount/currency from original payment when not specified (TZS refund was wrong otherwise)
    refund_currency = (body.currency or getattr(payment, "currency", "USD") or "USD").strip().upper()
    if body.amount is not None and str(body.amount).strip() != "":
        amount_raw = body.amount
    elif refund_currency == "TZS" and getattr(payment, "amount_tzs", 0) and int(payment.amount_tzs) > 0:
        amount_raw = str(int(payment.amount_tzs))
    else:
        amount_raw = str(payment.amount_usd)
    amount_str = f"{float(amount_raw):.2f}" if refund_currency == "USD" else str(int(float(amount_raw)))

    try:
        cybs = _cybs_client()
        resp = cybs.refund_payment(payment_id=payment.provider_ref, client_ref=f"refund-{b.booking_ref}", amount=amount_str, currency=refund_currency)
    except CybersourceError as e:
        log_audit(db, actor_user_id=user.email, action="refund_failed", entity_type="booking", entity_id=b.booking_ref, details={"error": str(e)})
        raise HTTPException(status_code=502, detail=str(e))

    payment.status = "refunded"
    b.payment_status = "refunded"
    b.status = "REFUNDED"
    log_audit(db, actor_user_id=user.email, action="refunded", entity_type="booking", entity_id=b.booking_ref, details={"cybs": resp})
    db.commit()
    return {"ok": True, "bookingRef": b.booking_ref, "refund": resp}

@router.post("/webhooks/cybersource")
async def cybersource_webhook(req: Request, db: Session = Depends(get_db)):
    body = await req.body()
    if settings.CYBS_WEBHOOK_VERIFY:
        path = (settings.CYBS_WEBHOOK_PATH or req.url.path).strip() or req.url.path
        ok = _verify_cybs_webhook(dict(req.headers), body, method=req.method, path=path)
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = json.loads(body.decode("utf-8") or "{}")

    # Cybersource notification formats vary by product; we support common shapes.
    cri = payload.get("clientReferenceInformation") or {}
    booking_ref = cri.get("code") or payload.get("bookingRef") or payload.get("booking_ref")
    provider_ref = (payload.get("id") or (payload.get("transactionInformation") or {}).get("id") or "")
    status = (payload.get("status") or payload.get("eventType") or payload.get("event_type") or "").upper()

    if booking_ref:
        log_audit(db, actor_user_id="cybersource", action="webhook_received", entity_type="booking", entity_id=str(booking_ref), details={"status": status})
        # Mark paid on SUCCESS events
        success_markers = ("SUCCEEDED", "SUCCESS", "COMPLETED", "AUTHORIZED", "CAPTURED", "PAID", "TRANSACTION.SUCCEEDED")
        if any(s in status for s in success_markers):
            _confirm_booking_paid_from_webhook(db, booking_ref=str(booking_ref), provider_ref=str(provider_ref), status=status, details={"payload": payload})
    return {"ok": True}


@router.post("/public/payments/cybersource/capture-context")
def cybersource_capture_context(body: CaptureContextRequest, db: Session = Depends(get_db)):
    """Generate a Microform/Flex capture context for the browser.

    This does NOT take card data. It returns a JWT/session used by Cybersource JS.
    """
    cybs = _cybs_client()

    target_origins = body.targetOrigins or [o.strip() for o in settings.CYBS_TARGET_ORIGINS.split(",") if o.strip()]
    client_version = body.clientVersion or settings.CYBS_CLIENT_VERSION
    allowed_networks = body.allowedCardNetworks or [c.strip() for c in settings.CYBS_ALLOWED_CARD_NETWORKS.split(",") if c.strip()]
    allowed_payment_types = body.allowedPaymentTypes or ["CARD"]

    # Prefer microform v2 sessions.
    resp = cybs.capture_context_microform(
        target_origins=target_origins,
        client_version=client_version,
        allowed_card_networks=allowed_networks,
        allowed_payment_types=allowed_payment_types,
    )
    js_url = settings.CYBS_MICROFORM_JS_URL or (
        "https://" + settings.CYBS_HOST + "/microform/v2/microform.min.js"
    )
    return {"captureContext": resp.get("captureContext") or resp.get("token") or resp, "microformJsUrl": js_url}


@router.post("/public/payments/cybersource/transient-token")
def cybersource_pay_with_transient_token(req: CybersourceTransientTokenRequest, db: Session = Depends(get_db)):
    """PCI-safe payment using Microform transientTokenJwt."""
    b = db.query(Booking).filter(Booking.booking_ref == req.bookingRef).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_hold_valid(b)
    if b.payment_status == "paid":
        return {"ok": True, "bookingRef": b.booking_ref, "paymentStatus": "paid"}

    amount_usd = _booking_amount_usd(db, b)
    client_ref = b.booking_ref
    currency = (req.currency or "USD").strip().upper()
    if currency == "TZS":
        total_tzs = getattr(b, "total_tzs", None)
        if total_tzs is not None and int(total_tzs) > 0:
            amount_to_charge = int(total_tzs)
        else:
            amount_to_charge = amount_usd * get_usd_to_tzs_rate(db)
    else:
        amount_to_charge = amount_usd
        currency = "USD"

    amount_str = f"{amount_to_charge:.2f}" if currency == "USD" else str(int(amount_to_charge))

    try:
        cybs = _cybs_client()
        resp = cybs.sale_transient_token(
            client_ref=client_ref,
            amount=amount_str,
            currency=currency,
            transient_token_jwt=req.transientTokenJwt,
            bill_to=req.billTo.model_dump() if req.billTo else None,
            capture=req.capture,
        )
    except CybersourceError as e:
        log_audit(db, actor_user_id="public", action="payment_failed", entity_type="booking", entity_id=b.booking_ref, details={"error": str(e)})
        raise HTTPException(status_code=502, detail=str(e))

    cybs_id = str(resp.get("id") or "")
    status = str(resp.get("status") or "").upper()

    amount_tzs = int(amount_to_charge) if currency == "TZS" else 0
    p = Payment(
        id=str(uuid.uuid4()),
        booking_id=b.id,
        provider="cybersource",
        amount_usd=amount_usd,
        amount_tzs=amount_tzs,
        currency=currency,
        status="paid" if status not in ("DECLINED", "REJECTED", "FAILED") else "failed",
        provider_ref=cybs_id or client_ref,
    )
    db.add(p)

    if p.status == "paid":
        b.payment_status = "paid"
        b.status = "CONFIRMED"
        log_audit(db, actor_user_id="public", action="payment_paid", entity_type="booking", entity_id=b.booking_ref, details={"cybs": {"id": cybs_id, "status": status}})
        _notify_pilot_if_assigned(db, b)
        _generate_ticket_for_booking(db, b)
        # Update booker email from billing if it was a placeholder
        if req.billTo:
            bill_email = (req.billTo.email or "").strip().lower()
            if bill_email and b.user_id:
                booker = db.get(User, b.user_id)
                if booker and (booker.email or "").lower() in ("customer@flysunbird.local", ""):
                    booker.email = bill_email
    else:
        b.payment_status = "failed"
        b.status = "PAYMENT_FAILED"
        log_audit(db, actor_user_id="public", action="payment_declined", entity_type="booking", entity_id=b.booking_ref, details={"cybs": {"id": cybs_id, "status": status}})

    db.commit()

    return {
        "ok": p.status == "paid",
        "bookingRef": b.booking_ref,
        "paymentStatus": b.payment_status,
        "cybersource": {"id": cybs_id, "status": status},
    }
