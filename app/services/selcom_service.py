"""
Selcom Tanzania payment gateway: create checkout order (redirect to mobile money / card).
Base URL: https://apigw.selcommobile.com/v1
API docs: https://developers.selcommobile.com/
Do not share API credentials. Ensure server IP is whitelisted (see RUN.md).
"""
from __future__ import annotations
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_checkout_order(
    order_id: str,
    amount: int,
    buyer_name: str,
    buyer_email: str,
    buyer_phone: str,
    currency: str = "TZS",
) -> dict[str, Any]:
    """
    Create a Selcom checkout order via /create-order-minimal.
    Returns API response; frontend redirects to data.link or data[0].link.
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
    # Base URL already includes /v1 (e.g. https://apigw.selcommobile.com/v1)
    order_path = "/checkout/create-order-minimal"
    order_data = {
        "vendor": vendor,
        "order_id": order_id,
        "buyer_email": (buyer_email or "customer@flysunbird.co.tz")[:255],
        "buyer_name": (buyer_name or "Customer")[:120],
        "buyer_phone": (buyer_phone or "255000000000").replace(" ", "")[:20],
        "amount": amount,
        "currency": currency.upper() or "TZS",
        "buyer_remarks": "FlySunbird booking " + order_id,
        "merchant_remarks": order_id,
        "no_of_items": 1,
    }
    response = client.postFunc(order_path, order_data)
    if not isinstance(response, dict):
        response = {}
    return response
