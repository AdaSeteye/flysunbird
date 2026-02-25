from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    from_label: Mapped[str] = mapped_column(String(120))
    to_label: Mapped[str] = mapped_column(String(120))
    main_region: Mapped[str] = mapped_column(String(20), default="MAINLAND")
    sub_region: Mapped[str] = mapped_column(String(80), nullable=True)
    region: Mapped[str] = mapped_column(String(80), default="Tanzania")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
