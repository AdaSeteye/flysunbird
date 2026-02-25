from pydantic import BaseModel, Field
from typing import Optional


class RefundRequest(BaseModel):
    """Used for Stripe (and any future) refunds."""
    bookingRef: str
    amount: Optional[str] = None
    currency: str = "USD"


class StripeCreateCheckoutSessionRequest(BaseModel):
    bookingRef: str
    currency: str = "USD"
    successUrl: Optional[str] = None  # If omitted, backend uses CLIENT_BASE_URL + /fly/confirmation.html?ref=...
    cancelUrl: Optional[str] = None   # If omitted, backend uses CLIENT_BASE_URL + /fly/payment.html?bookingRef=...
