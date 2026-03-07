import re
from pydantic import BaseModel, Field
from typing import Optional


class RefundRequest(BaseModel):
    """Used for Selcom (and any future) refunds."""
    bookingRef: str
    amount: Optional[str] = None
    currency: str = "USD"


def _is_valid_tanzania_mobile(s: str) -> bool:
    """Tanzania mobile: 9 digits after 255, first digit 6|7|8 (M-Pesa, Tigo, Airtel)."""
    if not s:
        return False
    digits = "".join(c for c in str(s) if c.isdigit())
    nine = digits[1:] if len(digits) == 10 and digits.startswith("0") else digits[3:] if len(digits) == 12 and digits.startswith("255") else digits if len(digits) == 9 else ""
    return len(nine) == 9 and bool(re.match(r"^[678]\d{8}$", nine))


def _normalize_tanzania_phone(s: str) -> str:
    """Return 255XXXXXXXXX or empty if invalid."""
    if not s:
        return ""
    digits = "".join(c for c in str(s) if c.isdigit())
    nine = digits[1:] if len(digits) == 10 and digits.startswith("0") else digits[3:] if len(digits) == 12 and digits.startswith("255") else digits if len(digits) == 9 else ""
    if len(nine) != 9 or not re.match(r"^[678]\d{8}$", nine):
        return ""
    return "255" + nine


class SelcomCreateOrderRequest(BaseModel):
    bookingRef: str
    buyerPhone: Optional[str] = None  # Valid Tanzania mobile; required for mobile money
    successUrl: Optional[str] = None
    cancelUrl: Optional[str] = None
