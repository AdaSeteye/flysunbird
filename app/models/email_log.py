from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    to_email: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # stored for worker retry
    status: Mapped[str] = mapped_column(String(30), default="queued")  # queued, sent, failed
    related_booking_ref: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
