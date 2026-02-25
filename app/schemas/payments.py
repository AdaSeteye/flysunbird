from pydantic import BaseModel, Field
from typing import Optional, List


class BillTo(BaseModel):
    firstName: str = Field(default="")
    lastName: str = Field(default="")
    address1: str = Field(default="")
    address2: str = Field(default="")
    locality: str = Field(default="")
    administrativeArea: str = Field(default="")
    postalCode: str = Field(default="")
    country: str = Field(default="TZ")
    email: str = Field(default="")
    phoneNumber: str = Field(default="")


class CardIn(BaseModel):
    # Raw card input: for PCI compliance in production, use Microform + transientTokenJwt (card never touches server).
    number: str
    expirationMonth: str
    expirationYear: str
    securityCode: Optional[str] = None
    type: Optional[str] = None


class CybersourceSaleRequest(BaseModel):
    bookingRef: str
    billTo: BillTo
    card: CardIn
    currency: str = "USD"


class CybersourceTransientTokenRequest(BaseModel):
    bookingRef: str
    transientTokenJwt: str
    billTo: Optional[BillTo] = None
    currency: str = "USD"
    capture: bool = True


class CybersourceRefundRequest(BaseModel):
    bookingRef: str
    amount: Optional[str] = None
    currency: str = "USD"


class CaptureContextRequest(BaseModel):
    # If omitted, backend uses env defaults.
    targetOrigins: Optional[List[str]] = None
    clientVersion: Optional[str] = None
    allowedCardNetworks: Optional[List[str]] = None
    allowedPaymentTypes: Optional[List[str]] = None  # usually ["CARD"]
