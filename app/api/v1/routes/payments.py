from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
import json
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import get_db
from app.api.deps import require_roles
from app.core.config import settings

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
from app.services.settings_service import get_usd_to_tzs_rate
from app.schemas.payments import RefundRequest, StripeCreateCheckoutSessionRequest

router = APIRouter(tags=["payments"])


def _confirm_booking_paid_from_webhook(db: Session, booking_ref: str, provider_ref: str, status: str, details: dict, provider: str = "stripe"):
    b = db.query(Booking).filter(Booking.booking_ref == booking_ref).first()
    if not b:
        return
    # idempotent
    if b.payment_status == "paid" and b.status == "CONFIRMED":
        return
    b.payment_status = "paid"
    b.status = "CONFIRMED"
    # update or create payment record for this provider
    p = db.query(Payment).filter(Payment.booking_id == b.id, Payment.provider == provider).order_by(Payment.created_at.desc()).first()
    if not p:
        p = Payment(id=str(uuid.uuid4()), booking_id=b.id, provider=provider,
                    amount_usd=getattr(b, "total_usd", 0) or 0, amount_tzs=getattr(b, "total_tzs", 0) or 0,
                    currency=getattr(b, "currency", "USD") or "USD", status="paid", provider_ref=provider_ref)
        db.add(p)
    else:
        p.status = "paid"
        p.provider_ref = provider_ref or p.provider_ref

    log_audit(db, actor_user_id=provider, action="payment_paid_webhook", entity_type="booking", entity_id=b.booking_ref, details={"status": status, **details})
    _notify_pilot_if_assigned(db, b)
    _generate_ticket_for_booking(db, b)
    db.commit()


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


# ---------- Stripe Checkout (redirect) ----------
@router.post("/public/payments/stripe/create-checkout-session")
def stripe_create_checkout_session(req: StripeCreateCheckoutSessionRequest, db: Session = Depends(get_db)):
    """Create a Stripe Checkout Session and return the URL for redirect. No card data on our server."""
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_SECRET_KEY.strip()):
        raise HTTPException(status_code=503, detail="Stripe is not configured (STRIPE_SECRET_KEY missing)")
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    b = db.query(Booking).filter(Booking.booking_ref == req.bookingRef).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_hold_valid(b)
    if b.payment_status == "paid":
        return {"ok": True, "bookingRef": b.booking_ref, "paymentStatus": "paid", "url": None}

    amount_usd = _booking_amount_usd(db, b)
    currency = (req.currency or "USD").strip().upper()
    if currency == "TZS":
        total_tzs = getattr(b, "total_tzs", None)
        if total_tzs is not None and int(total_tzs) > 0:
            amount_to_charge = int(total_tzs)
        else:
            amount_to_charge = int(amount_usd * get_usd_to_tzs_rate(db))
        currency_stripe = "tzs"
    else:
        currency_stripe = "usd"
        amount_to_charge = int(round(amount_usd * 100))  # cents

    base = (settings.CLIENT_BASE_URL or "").rstrip("/")
    if not base and req.successUrl:
        base = req.successUrl[: req.successUrl.rfind("/")]
    success_url = req.successUrl or (f"{base}/fly/confirmation.html?ref={b.booking_ref}" if base else None)
    cancel_url = req.cancelUrl or (f"{base}/fly/payment.html?bookingRef={b.booking_ref}" if base else None)
    if not success_url or not cancel_url:
        raise HTTPException(status_code=400, detail="CLIENT_BASE_URL or successUrl/cancelUrl required for Stripe Checkout")

    try:
        session_params = {
            "mode": "payment",
            "payment_method_types": ["card"],
            "line_items": [{
                "quantity": 1,
                "price_data": {
                    "currency": currency_stripe,
                    "unit_amount": amount_to_charge,
                    "product_data": {
                        "name": f"Flight booking {b.booking_ref}",
                        "description": f"FlySunbird booking {b.booking_ref}",
                    },
                },
            }],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"booking_ref": b.booking_ref},
            "client_reference_id": b.booking_ref,
        }
        session = stripe.checkout.Session.create(**session_params)
    except Exception as e:
        log_audit(db, actor_user_id="public", action="payment_failed", entity_type="booking", entity_id=b.booking_ref, details={"stripe_error": str(e)})
        raise HTTPException(status_code=502, detail=str(e))

    amount_tzs = int(amount_to_charge) if currency_stripe == "tzs" else 0
    p = Payment(
        id=str(uuid.uuid4()),
        booking_id=b.id,
        provider="stripe",
        amount_usd=amount_usd,
        amount_tzs=amount_tzs,
        currency=(currency_stripe or "usd").upper(),
        status="pending",
        provider_ref=session.id,
    )
    db.add(p)
    db.commit()

    return {"ok": True, "url": session.url, "sessionId": session.id, "bookingRef": b.booking_ref}


@router.post("/webhooks/stripe")
async def stripe_webhook(req: Request, db: Session = Depends(get_db)):
    """Handle Stripe checkout.session.completed and mark booking paid."""
    body = await req.body()
    sig = req.headers.get("stripe-signature") or ""
    if settings.STRIPE_WEBHOOK_SECRET and settings.STRIPE_WEBHOOK_SECRET.strip():
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            event = stripe.Webhook.construct_event(body, sig, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    else:
        import json
        event = json.loads(body.decode("utf-8") or "{}")

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        booking_ref = (session.get("metadata") or {}).get("booking_ref") or session.get("client_reference_id")
        if booking_ref:
            _confirm_booking_paid_from_webhook(
                db, booking_ref=booking_ref, provider_ref=session.get("id", ""), status="completed", details={"stripe_session": session.get("id")}, provider="stripe"
            )
    return {"ok": True}


@router.post("/ops/payments/stripe/refund")
def stripe_refund(body: RefundRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("ops", "finance", "admin", "superadmin"))):
    """Refund a Stripe payment (bookingRef, optional amount/currency)."""
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_SECRET_KEY.strip()):
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    b = db.query(Booking).filter(Booking.booking_ref == body.bookingRef).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b.payment_status != "paid":
        raise HTTPException(status_code=409, detail="Booking is not paid")

    payment = db.query(Payment).filter(
        Payment.booking_id == b.id,
        Payment.provider == "stripe",
        Payment.status == "paid",
    ).order_by(Payment.created_at.desc()).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Stripe payment not found for this booking")

    refund_currency = (body.currency or payment.currency or "USD").strip().upper()
    if body.amount is not None and str(body.amount).strip() != "":
        amount_raw = body.amount
    elif refund_currency == "TZS" and getattr(payment, "amount_tzs", 0) and int(payment.amount_tzs) > 0:
        amount_raw = str(int(payment.amount_tzs))
    else:
        amount_raw = str(payment.amount_usd)
    if refund_currency == "USD":
        refund_amount_cents = int(round(float(amount_raw) * 100))
    else:
        refund_amount_cents = int(float(amount_raw))  # TZS whole units

    try:
        session = stripe.checkout.Session.retrieve(payment.provider_ref, expand=["payment_intent"])
        pi = session.payment_intent if hasattr(session, "payment_intent") else (session.get("payment_intent") if isinstance(session, dict) else None)
        if not pi:
            pi_id = session.get("payment_intent") if isinstance(session, dict) else None
            if pi_id and isinstance(pi_id, str):
                pi = stripe.PaymentIntent.retrieve(pi_id)
            else:
                raise HTTPException(status_code=502, detail="Could not get payment intent from Stripe session")
        payment_intent_id = pi.id if hasattr(pi, "id") else pi.get("id")
        refund_params = {"payment_intent": payment_intent_id}
        if refund_currency == "USD" and refund_amount_cents > 0:
            refund_params["amount"] = refund_amount_cents
        elif refund_currency == "TZS" and refund_amount_cents > 0:
            refund_params["amount"] = refund_amount_cents
        stripe.Refund.create(**refund_params)
    except stripe.error.StripeError as e:
        log_audit(db, actor_user_id=user.email, action="refund_failed", entity_type="booking", entity_id=b.booking_ref, details={"error": str(e)})
        raise HTTPException(status_code=502, detail=str(e))

    payment.status = "refunded"
    b.payment_status = "refunded"
    b.status = "REFUNDED"
    log_audit(db, actor_user_id=user.email, action="refunded", entity_type="booking", entity_id=b.booking_ref, details={"provider": "stripe"})
    db.commit()
    return {"ok": True, "bookingRef": b.booking_ref, "provider": "stripe"}
