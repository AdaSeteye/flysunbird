from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class SlotRule(Base):
    __tablename__ = "slot_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), index=True)
    # comma-separated days: 0=Mon..6=Sun
    days_of_week: Mapped[str] = mapped_column(String(30), default="0,1,2,3,4,5,6")
    times: Mapped[str] = mapped_column(String(200), default="09:00,11:00,13:00,16:00")  # start times
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    price_usd: Mapped[int] = mapped_column(Integer, default=298)
    price_tzs: Mapped[int] = mapped_column(Integer, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=3)
    flight_no_prefix: Mapped[str] = mapped_column(String(20), default="FSB")
    cabin: Mapped[str] = mapped_column(String(30), default="Economy")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
