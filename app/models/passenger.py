from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(36), index=True)

    first: Mapped[str] = mapped_column(String(100))
    last: Mapped[str] = mapped_column(String(100))
    gender: Mapped[str] = mapped_column(String(20), default="")
    dob: Mapped[str] = mapped_column(String(20), default="")  # keep as string to match UI; validate in service
    nationality: Mapped[str] = mapped_column(String(80), default="")
    id_type: Mapped[str] = mapped_column(String(50), default="")
    id_number: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
