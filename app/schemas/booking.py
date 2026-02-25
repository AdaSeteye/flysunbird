from pydantic import BaseModel
from typing import List, Optional

class PassengerIn(BaseModel):
    first: str
    last: str
    phone: Optional[str] = ""
    gender: Optional[str] = ""
    dob: Optional[str] = ""
    nationality: Optional[str] = ""
    idType: Optional[str] = ""
    idNumber: Optional[str] = ""

class BookingCreate(BaseModel):
    timeEntryId: str
    pax: int = 1
    bookerEmail: str  # plain str to allow .local and other dev domains
    bookerName: str = ""
    passengers: List[PassengerIn]

class BookingOut(BaseModel):
    bookingRef: str
    status: str
    paymentStatus: str
    holdExpiresAt: Optional[str] = None
    unitPriceUSD: int = 0
    unitPriceTZS: int = 0
    totalUSD: int = 0
    totalTZS: int
    currency: str = "USD"
    exchangeRateUsed: int | None = None
