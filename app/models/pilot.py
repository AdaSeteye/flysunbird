from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class PilotAssignment(Base):
    __tablename__ = "pilot_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    time_entry_id: Mapped[str] = mapped_column(String(36), index=True)
    pilot_user_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned")  # assigned, accepted, completed
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
