from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region: Mapped[str] = mapped_column(String(80), default="Tanzania")
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subs_csv: Mapped[str] = mapped_column(String(600), default="")
    active: Mapped[bool] = mapped_column(Boolean(), default=True)

    @property
    def subs(self):
        return [s.strip() for s in (self.subs_csv or "").split(",") if s.strip()]
