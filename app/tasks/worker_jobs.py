from datetime import datetime, timezone, timedelta, date
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError
from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.time_entry import TimeEntry
from app.models.slot_rule import SlotRule
from app.models.route import Route
from app.services.settings_service import get_usd_to_tzs_rate
from app.services.weekly_plan_service import import_weekly_plan
from app.services.email_service import process_pending_emails
from app.schemas.ops import WeeklyPlanImportRequest

def expire_holds():
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        try:
            expired = db.query(Booking).filter(
                Booking.status == "PENDING_PAYMENT",
                Booking.payment_status.in_(["pending", "unpaid"]),
                Booking.hold_expires_at != None,
                Booking.hold_expires_at < now,
            ).all()
        except ProgrammingError:
            # DB not migrated yet; don't crash the worker.
            db.rollback()
            return {"skipped": True, "reason": "missing_tables"}
        for b in expired:
            te = db.get(TimeEntry, b.time_entry_id)
            if te:
                te.seats_available += b.pax
            b.status = "EXPIRED"
            b.payment_status = "unpaid"
        db.commit()
        return {"expired": len(expired)}
    finally:
        db.close()

def _end_time(start_hhmm: str, dur_min: int) -> str:
    hh, mm = map(int, start_hhmm.split(":"))
    total = hh*60 + mm + dur_min
    total %= 1440
    eh, em = divmod(total, 60)
    return f"{eh:02d}:{em:02d}"

def generate_slots():
    db: Session = SessionLocal()
    try:
        try:
            rules = db.query(SlotRule).filter(SlotRule.active == True).all()
        except ProgrammingError:
            db.rollback()
            return {"skipped": True, "reason": "missing_tables"}
        today = datetime.now(timezone.utc).date()
        # Track (route_id, date_str, start) added this run so we don't double-insert before commit
        added_keys = set()
        for r in rules:
            route = db.get(Route, r.route_id)
            if not route:
                continue
            days = {int(x) for x in (r.days_of_week or "").split(",") if x.strip().isdigit()}
            times = [t.strip() for t in (r.times or "").split(",") if t.strip()]
            for i in range(r.horizon_days):
                d = today + timedelta(days=i)
                if days and d.weekday() not in days:
                    continue
                date_str = d.isoformat()
                for t in times:
                    key = (r.route_id, date_str, t)
                    if key in added_keys:
                        continue
                    exists = db.query(TimeEntry).filter_by(route_id=r.route_id, date_str=date_str, start=t).first()
                    if exists:
                        continue
                    added_keys.add(key)
                    end = _end_time(t, r.duration_minutes)
                    db.add(TimeEntry(
                        id=str(uuid.uuid4()),
                        route_id=r.route_id,
                        date_str=date_str,
                        start=t,
                        end=end,
                        price_usd=r.price_usd,
                        price_tzs=(r.price_tzs if getattr(r,'price_tzs', None) is not None else int(r.price_usd * get_usd_to_tzs_rate(db))),
                        seats_available=r.capacity,
                        flight_no=f"{r.flight_no_prefix}{d.strftime('%m%d')}",
                        cabin=r.cabin,
                    ))
        db.commit()
    finally:
        db.close()


def apply_regular_weekly_plan(weeks_ahead: int = 4):
    """
    Apply the regular 5H-FSA weekly plan for the next N weeks so customers and admin
    always see slots from the standard schedule (no manual import).
    """
    db: Session = SessionLocal()
    try:
        try:
            db.query(TimeEntry).limit(1).first()
        except ProgrammingError:
            db.rollback()
            return {"skipped": True, "reason": "missing_tables"}
        today = date.today()
        # Monday of current week (0=Mon)
        monday = today - timedelta(days=today.weekday())
        total_created = 0
        for i in range(weeks_ahead):
            week_start = monday + timedelta(days=7 * i)
            week_str = week_start.isoformat()
            body = WeeklyPlanImportRequest(
                week_start_date=week_str,
                plan_id="5H-FSA",
                default_price_usd=298,
                default_capacity=3,
            )
            result = import_weekly_plan(db, body)
            total_created += result.time_entries_created
        db.commit()
        return {"ok": True, "time_entries_created": total_created}
    finally:
        db.close()


def process_email_queue(limit: int = 50) -> dict:
    """Process queued/failed emails (retry send). Run periodically via Celery beat."""
    db: Session = SessionLocal()
    try:
        try:
            return process_pending_emails(db, limit=limit)
        except ProgrammingError:
            db.rollback()
            return {"skipped": True, "reason": "missing_tables"}
    finally:
        db.close()
