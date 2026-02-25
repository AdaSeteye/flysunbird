from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    time_entry_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)  # booker

    created_by_role: Mapped[str] = mapped_column(String(12), default="USER")  # USER|OPS
    currency: Mapped[str] = mapped_column(String(3), default="USD")          # USD|TZS
    exchange_rate_used: Mapped[int] = mapped_column(Integer, nullable=True)

    pax: Mapped[int] = mapped_column(Integer, default=1)

    unit_price_usd: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_tzs: Mapped[int] = mapped_column(Integer, default=0)
    total_usd: Mapped[int] = mapped_column(Integer, default=0)
    total_tzs: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(30), default="PENDING_PAYMENT")  # pending_payment, confirmed, cancelled, completed, expired
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid")   # unpaid, pending, paid, refunded

    hold_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    ticket_object_key: Mapped[str] = mapped_column(String(512), nullable=True)
    ticket_storage: Mapped[str] = mapped_column(String(16), default="local")
    ticket_status: Mapped[str] = mapped_column(String(30), default="none")  # none, generated, invalid

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
