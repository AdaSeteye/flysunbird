import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.db.session import SessionLocal
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.models.route import Route
from app.models.slot_rule import SlotRule
from app.models.time_entry import TimeEntry
from app.models.booking import Booking
from app.models.setting import Setting


def ensure_user(db: Session, email: str, password: str, role: str, name: str):
    u = db.query(User).filter(User.email == email).first()
    if u:
        return
    db.add(
        User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=name,
            role=role,
            password_hash=hash_password(password),
            is_active=True,
        )
    )
    db.commit()


def run(db=None):
    if db is None:
        db = SessionLocal()
    try:
        # If migrations haven't been applied yet, seeding must not crash the API.
        try:
            db.execute(text("SELECT 1 FROM users LIMIT 1"))
        except ProgrammingError:
            db.rollback()
            print("[seed] users table not found yet. Skipping seeding (run alembic upgrade head).")
            return

        # roles
        ensure_user(db, "admin@flysunbird.co.tz", "admin12345", "admin", "Admin")
        ensure_user(db, "ops@flysunbird.co.tz", "ops12345", "ops", "OPS")
        ensure_user(db, "finance@flysunbird.co.tz", "finance12345", "finance", "Finance")
        ensure_user(db, "pilot@flysunbird.co.tz", "pilot12345", "pilot", "Pilot")

        # settings
        s = db.get(Setting, "USD_TO_TZS")
        if not s:
            db.add(Setting(key="USD_TO_TZS", int_value=2450, str_value=None))
            db.commit()

        # routes – match 5H-FSA weekly plan only (Dar es Salaam = JNIA only; Zanzibar = AAKI, Paje, Nungwi, Seacliff)
        ROUTES = [
            ("Dar es Salaam Airport", "Zanzibar Airport"),
            ("Zanzibar Airport", "Dar es Salaam Airport"),
            ("Dar es Salaam Airport", "Zanzibar Seacliff"),
            ("Zanzibar Seacliff", "Zanzibar Airport"),
            ("Zanzibar Airport", "Zanzibar Nungwi"),
            ("Zanzibar Nungwi", "Zanzibar Seacliff"),
            ("Zanzibar Nungwi", "Dar es Salaam Airport"),
            ("Zanzibar Airport", "Paje"),
            ("Paje", "Zanzibar Nungwi"),
        ]
        routes_created = []
        from app.services.weekly_plan_service import get_main_region_for_label
        for from_label, to_label in ROUTES:
            exists = db.query(Route).filter(
                Route.from_label == from_label,
                Route.to_label == to_label,
            ).first()
            if not exists:
                r = Route(
                    id=str(uuid.uuid4()),
                    from_label=from_label,
                    to_label=to_label,
                    region="Tanzania",
                    main_region=get_main_region_for_label(from_label),
                )
                db.add(r)
                routes_created.append(r)
        if routes_created:
            db.commit()

        # slot rules = 5H-FSA weekly plan from weekly_plan_service (0=Mon..6=Sun, stored as-is)
        from app.services.weekly_plan_service import DEFAULT_PLAN_5H_FSA_LEGS, _resolve_label, get_or_create_route
        tzs_rate = 2450
        # Remove ALL slot rules so only 5H-FSA schedule remains (no legacy 30-min “all days” or other routes)
        db.query(SlotRule).delete(synchronize_session=False)
        # Remove all time entries that have no booking, so next generate_slots creates only 5H-FSA slots
        booked_te_ids = {r[0] for r in db.query(Booking.time_entry_id).filter(Booking.time_entry_id.isnot(None)).distinct().all()}
        if booked_te_ids:
            db.query(TimeEntry).filter(~TimeEntry.id.in_(booked_te_ids)).delete(synchronize_session=False)
        else:
            db.query(TimeEntry).delete(synchronize_session=False)
        db.flush()
        for leg in DEFAULT_PLAN_5H_FSA_LEGS:
            from_label = _resolve_label(leg["from_code"])
            to_label = _resolve_label(leg["to_code"])
            if not from_label or not to_label:
                continue
            route, _ = get_or_create_route(db, from_label, to_label)
            if not route:
                continue
            db.flush()
            db.add(
                SlotRule(
                    id=str(uuid.uuid4()),
                    route_id=route.id,
                    days_of_week=str(leg["day_of_week"]),
                    times=leg["start"],
                    duration_minutes=leg["duration_minutes"],
                    price_usd=298,
                    price_tzs=298 * tzs_rate,
                    capacity=3,
                    flight_no_prefix="FSB",
                    cabin="Economy",
                    active=True,
                    horizon_days=120,
                )
            )
        # Classify all routes into Dar es Salaam vs Zanzibar (main_region) from origin
        for r in db.query(Route).all():
            r.main_region = get_main_region_for_label(r.from_label)
        # Migrate legacy label: Seacliff is in Zanzibar, not Dar es Salaam
        for r in db.query(Route).all():
            if r.from_label == "Dar es Salaam Seacliff":
                r.from_label = "Zanzibar Seacliff"
            if r.to_label == "Dar es Salaam Seacliff":
                r.to_label = "Zanzibar Seacliff"
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
