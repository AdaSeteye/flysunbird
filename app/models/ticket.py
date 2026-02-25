from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.db.session import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)

    # storage backend: local | gcs
    storage_backend = Column(String(16), nullable=False, default="local")
    object_key = Column(String(512), nullable=False)  # local path or GCS object key
    mime_type = Column(String(64), nullable=False, default="application/pdf")
    status = Column(String(32), nullable=False, default="ACTIVE")  # ACTIVE | INVALIDATED

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    booking = relationship("Booking", back_populates="tickets")
