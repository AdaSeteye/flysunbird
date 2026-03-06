from __future__ import annotations
import base64
import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)
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
from app.services.email_service import queue_email, send_booking_confirmation_and_ticket, send_unpaid_ticket_email
from app.services.ticket_service import (
    render_ticket_pdf_bytes,
    store_ticket_pdf,
    build_ticket_context,
)
from app.services.settings_service import get_usd_to_tzs_rate
from app.schemas.payments import RefundRequest, StripeCreateCheckoutSessionRequest, SelcomCreateOrderRequest

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
    send_booking_confirmation_and_ticket(db, b.booking_ref)
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
    """Generate and store paid ticket PDF. Idempotent. Only for paid bookings."""
    if b.payment_status != "paid":
        return
    if b.ticket_status == "generated" and b.ticket_object_key:
        return
    ctx = build_ticket_context(db, b)
    if not ctx:
        return
    ctx["payment_status"] = "paid"
    pdf_bytes = render_ticket_pdf_bytes(**ctx)
    storage, object_key = store_ticket_pdf(booking_ref=b.booking_ref, pdf_bytes=pdf_bytes)
    b.ticket_storage = storage
    b.ticket_object_key = object_key
    b.ticket_status = "generated"
    db.commit()
    return


# ---------- Selcom Checkout (redirect to Selcom payment page) ----------
@router.post("/public/payments/selcom/create-order")
def selcom_create_order(req: SelcomCreateOrderRequest, db: Session = Depends(get_db)):
    """Create a Selcom checkout order; returns URL to redirect the customer to pay (mobile money / card)."""
    try:
        b = db.query(Booking).filter(Booking.booking_ref == req.bookingRef).first()
        if not b:
            raise HTTPException(status_code=404, detail="Booking not found")
        _ensure_hold_valid(b)
        if b.payment_status == "paid":
            return {"ok": True, "bookingRef": b.booking_ref, "paymentStatus": "paid", "url": None}

        amount_usd = _booking_amount_usd(db, b)
        rate = get_usd_to_tzs_rate(db)
        amount_tzs = int(amount_usd * rate) if rate else int(amount_usd * 2450)
        first_passenger = db.query(Passenger).filter(Passenger.booking_id == b.id).order_by(Passenger.created_at.asc()).first()
        buyer_name = ""
        buyer_phone = ""
        if first_passenger:
            buyer_name = f"{(first_passenger.first or '').strip()} {(first_passenger.last or '').strip()}".strip()
            buyer_phone = (first_passenger.phone or "").strip().replace(" ", "")
        buyer_email = (getattr(b, "contact_email", None) or "").strip()
        if not buyer_email and b.user_id:
            booker = db.get(User, b.user_id)
            if booker:
                buyer_email = (getattr(booker, "email", None) or "").strip()
        if not buyer_name:
            buyer_name = "Customer"

        from app.services.selcom_service import create_checkout_order, create_checkout_order_minimal

        client_base = (settings.CLIENT_BASE_URL or "").rstrip("/")
        api_public = (settings.API_PUBLIC_URL or "").rstrip("/")
        redirect_url = f"{client_base}/fly/confirmation.html?ref={b.booking_ref}" if client_base else None
        cancel_url = f"{client_base}/fly/payment.html?bookingRef={b.booking_ref}" if client_base else None
        webhook_url = f"{api_public}/api/v1/webhooks/selcom" if api_public else None

        common = dict(
            order_id=b.booking_ref,
            amount=amount_tzs,
            buyer_name=buyer_name,
            buyer_email=buyer_email or "customer@flysunbird.co.tz",
            buyer_phone=buyer_phone or "255000000000",
            currency="TZS",
            redirect_url=redirect_url,
            cancel_url=cancel_url,
            webhook_url=webhook_url,
        )
        # Try minimal first (many vendors only have this); fallback to full Create Order if no URL
        resp = create_checkout_order_minimal(**common)
        if resp.get("result") != "SUCCESS":
            resp = create_checkout_order(**common)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("[Selcom] create order failed: %s", e)
        booking_ref = getattr(req, "bookingRef", "")
        log_audit(db, actor_user_id="public", action="payment_failed", entity_type="booking", entity_id=booking_ref, details={"selcom_error": str(e)})
        try:
            send_unpaid_ticket_email(db, booking_ref)
        except Exception as email_err:
            logger.warning("[Selcom] Failed to send unpaid ticket email after failure: %s", email_err)
        raise HTTPException(status_code=502, detail=str(e))

    # Selcom response: structure may vary; try common keys for payment/redirect URL. for payment/redirect URL.
    # Create-order-minimal returns data[0].payment_gateway_url (base64-encoded per Selcom docs).
    def _decode_url(val: str) -> str:
        if not val or not isinstance(val, str):
            return val or ""
        for attempt in (val, val + "==", val + "="):  # try with padding
            for decoder in (base64.b64decode, base64.urlsafe_b64decode):
                try:
                    decoded = decoder(attempt).decode("utf-8")
                    if decoded.startswith("http://") or decoded.startswith("https://"):
                        return decoded
                except Exception:
                    continue
        return val

    logger.info("[Selcom] create-order order_id=%s response: %s", b.booking_ref, resp)
    # Print details so they always show in docker logs (for Selcom support)
    try:
        print("[Selcom] order_id=%s (booking_ref)" % (b.booking_ref,), flush=True)
        print("[Selcom] API response: result=%s resultcode=%s message=%s" % (
            resp.get("result"), resp.get("resultcode"), resp.get("message")), flush=True)
        print("[Selcom] Full response (for support): %s" % json.dumps(resp, default=str), flush=True)
    except Exception:
        pass

    def _extract_url(r: dict) -> str | None:
        out = None
        if not isinstance(r, dict):
            return None
        for key in ("url", "link", "payment_url", "redirect_url", "checkout_url"):
            if r.get(key) and isinstance(r.get(key), str):
                return r.get(key)
        data = r.get("data")
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                for key in ("payment_gateway_url", "link", "url", "payment_url", "redirect_url"):
                    if first.get(key) and isinstance(first.get(key), str):
                        raw = first.get(key)
                        out = _decode_url(raw) if key == "payment_gateway_url" else raw
                        if out and (out.startswith("http://") or out.startswith("https://")):
                            return out
        if isinstance(data, dict):
            for key in ("payment_gateway_url", "link", "url", "payment_url", "redirect_url"):
                if data.get(key) and isinstance(data.get(key), str):
                    raw = data.get(key)
                    out = _decode_url(raw) if key == "payment_gateway_url" else raw
                    if out and (out.startswith("http://") or out.startswith("https://")):
                        return out
        if not out and isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for key in ("payment_gateway_url", "link", "url", "payment_url", "redirect_url"):
                        if item.get(key) and isinstance(item.get(key), str):
                            raw = item.get(key)
                            out = _decode_url(raw) if key == "payment_gateway_url" else raw
                            if out and (out.startswith("http://") or out.startswith("https://")):
                                return out
                if out:
                    break
        return out

    url = _extract_url(resp)
    # If we have a URL from minimal but Selcom gateway often returns 404, try full create-order and use its URL (some vendors only serve full checkout).
    if url:
        try:
            from app.services.selcom_service import create_checkout_order
            client_base = (settings.CLIENT_BASE_URL or "").rstrip("/")
            api_public = (settings.API_PUBLIC_URL or "").rstrip("/")
            redirect_url = f"{client_base}/fly/confirmation.html?ref={b.booking_ref}" if client_base else None
            cancel_url = f"{client_base}/fly/payment.html?bookingRef={b.booking_ref}" if client_base else None
            webhook_url = f"{api_public}/api/v1/webhooks/selcom" if api_public else None
            resp_full = create_checkout_order(
                order_id=b.booking_ref, amount=amount_tzs, buyer_name=buyer_name,
                buyer_email=buyer_email or "customer@flysunbird.co.tz",
                buyer_phone=buyer_phone or "255000000000", currency="TZS",
                redirect_url=redirect_url, cancel_url=cancel_url, webhook_url=webhook_url,
            )
            if resp_full.get("result") == "SUCCESS":
                url_full = _extract_url(resp_full)
                if url_full and url_full != url:
                    url = url_full
                    logger.info("[Selcom] using full create-order URL (may avoid gateway 404)")
        except Exception as e:
            logger.warning("[Selcom] full create-order (optional) failed: %s", e)
    if not url:
        try:
            from app.services.selcom_service import create_checkout_order
            client_base = (settings.CLIENT_BASE_URL or "").rstrip("/")
            api_public = (settings.API_PUBLIC_URL or "").rstrip("/")
            redirect_url = f"{client_base}/fly/confirmation.html?ref={b.booking_ref}" if client_base else None
            cancel_url = f"{client_base}/fly/payment.html?bookingRef={b.booking_ref}" if client_base else None
            webhook_url = f"{api_public}/api/v1/webhooks/selcom" if api_public else None
            resp = create_checkout_order(
                order_id=b.booking_ref, amount=amount_tzs, buyer_name=buyer_name,
                buyer_email=buyer_email or "customer@flysunbird.co.tz",
                buyer_phone=buyer_phone or "255000000000", currency="TZS",
                redirect_url=redirect_url, cancel_url=cancel_url, webhook_url=webhook_url,
            )
            logger.info("[Selcom] full create-order fallback response: %s", resp)
            url = _extract_url(resp)
        except Exception as e:
            logger.warning("[Selcom] full create-order fallback failed: %s", e)
    if not url:
        msg = (resp.get("message") if isinstance(resp, dict) else None) or (resp.get("result") if isinstance(resp, dict) else None)
        detail = "Selcom did not return a payment URL."
        if msg:
            detail += f" Selcom: {msg}"
        logger.warning("[Selcom] response missing payment URL: %s", resp)
        raise HTTPException(status_code=502, detail=detail)

    try:
        p = Payment(
            id=str(uuid.uuid4()),
            booking_id=b.id,
            provider="selcom",
            amount_usd=amount_usd,
            amount_tzs=amount_tzs,
            currency="TZS",
            status="pending",
            provider_ref=b.booking_ref,
        )
        db.add(p)
        db.commit()
    except Exception as e:
        logger.exception("[Selcom] payment record save failed: %s", e)
        raise HTTPException(status_code=502, detail="Payment record failed")

    # Log exact redirect URL for Selcom support if gateway shows "Page Not Found"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        logger.info("[Selcom] redirect: host=%r path=%r", parsed.netloc, (parsed.path or "")[:80])
        logger.info("[Selcom] redirect full URL (share with Selcom if 404): %s", url)
        # print() so it always appears in docker logs (app logger may be WARNING)
        print(f"[Selcom] redirect URL (if 404, send to Selcom support): {url}", flush=True)
        print("[Selcom] --- end of create-order details ---", flush=True)
    except Exception:
        pass
    return {"ok": True, "url": url, "bookingRef": b.booking_ref}


@router.post("/webhooks/selcom")
async def selcom_webhook(req: Request, db: Session = Depends(get_db)):
    """Handle Selcom payment callback. On SUCCESS/COMPLETED mark booking paid."""
    body = await req.body()
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        payload = {}
    order_id = payload.get("order_id") or payload.get("transid")
    result = (payload.get("result") or "").upper()
    resultcode = payload.get("resultcode") or payload.get("resulcode", "")
    payment_status = (payload.get("payment_status") or "").upper()
    reference = payload.get("reference") or ""
    transid = payload.get("transid") or order_id
    logger.info("[Selcom] webhook: order_id=%s result=%s payment_status=%s", order_id, result, payment_status)

    if not order_id:
        logger.warning("[Selcom] webhook: missing order_id")
        return {"ok": True}
    booking_ref = order_id
    if result == "SUCCESS" and (payment_status == "COMPLETED" or resultcode == "000"):
        _confirm_booking_paid_from_webhook(
            db, booking_ref=booking_ref, provider_ref=transid or reference, status=payment_status or result, details=payload, provider="selcom"
        )
    return {"ok": True}


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
        try:
            send_unpaid_ticket_email(db, b.booking_ref)
        except Exception as email_err:
            logger.warning("[Stripe] Failed to send unpaid ticket email after failure: %s", email_err)
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
    logger.info("[Stripe] webhook received (body_len=%s, has_sig=%s)", len(body), bool(sig))

    if settings.STRIPE_WEBHOOK_SECRET and settings.STRIPE_WEBHOOK_SECRET.strip():
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            event = stripe.Webhook.construct_event(body, sig, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            logger.warning("[Stripe] webhook signature verification failed: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    else:
        logger.warning("[Stripe] STRIPE_WEBHOOK_SECRET not set; accepting payload without verification (not for production)")
        event = json.loads(body.decode("utf-8") or "{}")

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        booking_ref = (session.get("metadata") or {}).get("booking_ref") or session.get("client_reference_id")
        if booking_ref:
            logger.info("[Stripe] checkout.session.completed for booking_ref=%s", booking_ref)
            _confirm_booking_paid_from_webhook(
                db, booking_ref=booking_ref, provider_ref=session.get("id", ""), status="completed", details={"stripe_session": session.get("id")}, provider="stripe"
            )
        else:
            logger.warning("[Stripe] webhook: checkout.session.completed but no booking_ref in session")
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
