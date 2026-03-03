"""
Selcom Tanzania payment gateway: create checkout order (redirect to mobile money / card).
Base URL: https://apigw.selcommobile.com/v1
API docs: https://developers.selcommobile.com/
Do not share API credentials. Ensure server IP is whitelisted (see RUN.md).
Note: All URLs in request and response are base64-encoded per Selcom docs.
"""
from __future__ import annotations
import base64
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _b64_url(url: str) -> str:
    """Base64-encode URL for Selcom request (all URLs must be base64 per docs)."""
    if not url or not isinstance(url, str):
        return ""
    return base64.b64encode(url.encode("utf-8")).decode("ascii")


def create_checkout_order(
    order_id: str,
    amount: int,
    buyer_name: str,
    buyer_email: str,
    buyer_phone: str,
    currency: str = "TZS",
    *,
    redirect_url: str | None = None,
    cancel_url: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """
    Create a Selcom checkout order via full Create Order API (payment_methods ALL)
    so both card and mobile money work. Returns API response; frontend redirects
    to data[0].payment_gateway_url (base64-decoded).
    Optional redirect_url, cancel_url, webhook_url must be plain URLs; we base64-encode.
    """
    base = (settings.SELCOM_BASE_URL or "").rstrip("/")
    key = (settings.SELCOM_API_KEY or "").strip()
    secret = (settings.SELCOM_API_SECRET or "").strip()
    vendor = (settings.SELCOM_VENDOR or "").strip()
    if not all([base, key, secret, vendor]):
        raise ValueError("Selcom is not configured (SELCOM_BASE_URL, SELCOM_API_KEY, SELCOM_API_SECRET, SELCOM_VENDOR)")

    try:
        from selcom_apigw_client import apigwClient
    except ImportError:
        raise ValueError("selcom-apigw-client not installed. pip install selcom-apigw-client")

    client = apigwClient.Client(base, key, secret)

    # Full Create Order: supports cards + mobile money. Requires billing (flat structure in client).
    # Path relative to base (base already has /v1)
    order_path = "/checkout/create-order"

    # Billing required for card payments (doc: "Card payments with no billing info will get rejected")
    first_name = (buyer_name or "Customer").split()[0][:60] if (buyer_name or "Customer").strip() else "Customer"
    last_name = " ".join((buyer_name or "Customer").split()[1:])[:60] if (buyer_name or "Customer").strip() else "Customer"
    if not last_name:
        last_name = first_name

    order_data = {
        "vendor": vendor,
        "order_id": order_id,
        "buyer_email": (buyer_email or "customer@flysunbird.co.tz")[:255],
        "buyer_name": (buyer_name or "Customer")[:120],
        "buyer_userid": "",
        "buyer_phone": (buyer_phone or "255000000000").replace(" ", "")[:20],
        "gateway_buyer_uuid": "",
        "amount": amount,
        "currency": (currency or "TZS").upper(),
        "payment_methods": "ALL",
        "buyer_remarks": "FlySunbird booking " + order_id,
        "merchant_remarks": order_id,
        "no_of_items": 1,
        # Billing (required for card)
        "billing.firstname": first_name,
        "billing.lastname": last_name,
        "billing.address_1": "FlySunbird Booking",
        "billing.address_2": "",
        "billing.city": "Dar es Salaam",
        "billing.state_or_region": "Dar es Salaam",
        "billing.postcode_or_pobox": "00000",
        "billing.country": "TZ",
        "billing.phone": (buyer_phone or "255000000000").replace(" ", "")[:20],
    }

    if redirect_url:
        order_data["redirect_url"] = _b64_url(redirect_url)
    if cancel_url:
        order_data["cancel_url"] = _b64_url(cancel_url)
    if webhook_url:
        order_data["webhook"] = _b64_url(webhook_url)

    response = client.postFunc(order_path, order_data)
    if not isinstance(response, dict):
        response = {}
    return response
