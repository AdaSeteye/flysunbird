from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class Cancellation(Base):
    __tablename__ = "cancellations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(36), index=True)
    booking_ref: Mapped[str] = mapped_column(String(20), index=True)

    requested_by_user_id: Mapped[str] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")

    status: Mapped[str] = mapped_column(String(30), default="requested")  # requested, approved, rejected
    refund_amount_usd: Mapped[int] = mapped_column(Integer, default=0)

    decided_by_user_id: Mapped[str] = mapped_column(String(36), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
