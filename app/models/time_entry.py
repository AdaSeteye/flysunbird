from sqlalchemy import String, Date, Integer, DateTime, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        UniqueConstraint("route_id","date_str","start", name="uq_time_entry_route_date_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), index=True)

    # UI fields (must map to OPS payload)
    date_str: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    start: Mapped[str] = mapped_column(String(5))  # HH:MM
    end: Mapped[str] = mapped_column(String(5))    # HH:MM
    price_usd: Mapped[int] = mapped_column(Integer)
    price_tzs: Mapped[int] = mapped_column(Integer, nullable=True)
    seats_available: Mapped[int] = mapped_column(Integer)
    flight_no: Mapped[str] = mapped_column(String(30), default="FSB")
    cabin: Mapped[str] = mapped_column(String(30), default="Economy")

    # Booking-aligned controls
    visibility: Mapped[str] = mapped_column(String(12), default="PUBLIC")  # PUBLIC|HIDDEN
    status: Mapped[str] = mapped_column(String(12), default="PUBLISHED")   # DRAFT|PUBLISHED|CLOSED
    currency: Mapped[str] = mapped_column(String(3), default="USD")        # USD|TZS
    exchange_rate: Mapped[int] = mapped_column(Integer, nullable=True)     # USD->TZS at creation time

    base_price_usd: Mapped[int] = mapped_column(Integer, default=0)
    base_price_tzs: Mapped[int] = mapped_column(Integer, nullable=True)
    override_price_usd: Mapped[int] = mapped_column(Integer, nullable=True)
    override_price_tzs: Mapped[int] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
