from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class TimeEntryIn(BaseModel):
    route_id: str
    date_str: str
    start: str
    end: str
    price_usd: int
    price_tzs: int | None = None
    seats_available: int
    visibility: str = "PUBLIC"
    status: str = "PUBLISHED"
    currency: str = "USD"
    exchange_rate: int | None = None
    base_price_usd: int = 0
    base_price_tzs: int | None = None
    override_price_usd: int | None = None
    override_price_tzs: int | None = None
    flight_no: str = "FSB"
    cabin: str = "Economy"

class TimeEntryOut(TimeEntryIn):
    id: str
    from_label: Optional[str] = None
    to_label: Optional[str] = None

class SlotRuleIn(BaseModel):
    route_id: str
    days_of_week: str = "0,1,2,3,4,5,6"
    times: str = "09:00,11:00,13:00,16:00"
    duration_minutes: int = 30
    price_usd: int = 298
    price_tzs: int | None = None
    capacity: int = 3
    flight_no_prefix: str = "FSB"
    cabin: str = "Economy"
    active: bool = True
    horizon_days: int = 90

class SlotRuleOut(SlotRuleIn):
    id: str

class CancellationRequestIn(BaseModel):
    reason: str = ""

class CancellationDecisionIn(BaseModel):
    approve: bool = True
    refund_amount_usd: int = 0
    decision_note: str = ""

class CancellationOut(BaseModel):
    id: str
    bookingRef: str
    status: str
    refundAmountUSD: int = 0
    reason: str = ""
    createdAt: str
    decidedAt: Optional[str] = None

class DashboardSeriesPoint(BaseModel):
    date: str
    value: int

class WeeklyPlanLeg(BaseModel):
    """One leg from the weekly fleet operations plan. day_of_week: 0=Mon .. 6=Sun."""
    day_of_week: int = Field(ge=0, le=6)
    from_code: str = Field(description="Location code e.g. JNIA, AAKI, Nungwi")
    to_code: str = Field(description="Location code")
    start: str = Field(description="HH:MM departure")
    end: str = Field(description="HH:MM arrival")
    duration_minutes: int = Field(ge=1, le=300, description="Flight duration")

class WeeklyPlanImportRequest(BaseModel):
    """Import a weekly operations plan: create routes (if needed) and time entries for the given week."""
    week_start_date: str = Field(description="Monday of the week YYYY-MM-DD")
    legs: List[WeeklyPlanLeg] = Field(default_factory=list)
    plan_id: Optional[str] = Field(default=None, description="Use embedded preset e.g. '5H-FSA' (ignored if legs provided)")
    default_price_usd: int = 298
    default_capacity: int = 3
    flight_no_prefix: str = "FSB"

class WeeklyPlanImportResponse(BaseModel):
    routes_created: int = 0
    time_entries_created: int = 0
    errors: List[str] = Field(default_factory=list)

class DashboardMetrics(BaseModel):
    bookings_total: int
    bookings_paid: int
    bookings_pending: int
    cancellations_requested: int
    cancellations_approved: int
    revenue_usd_total: int
    seats_sold_total: int
    bookings_by_day: List[DashboardSeriesPoint]
    revenue_by_day: List[DashboardSeriesPoint]
