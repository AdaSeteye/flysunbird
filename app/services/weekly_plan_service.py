"""
Weekly fleet operations plan: presets (e.g. 5H-FSA), location aliases, and import.

Day-of-week convention (match schema ops.WeeklyPlanLeg and slot_rule.days_of_week):
  0 = Monday, 1 = Tuesday, ..., 6 = Sunday (Python datetime.weekday()).
Seed stores days_of_week as-is; generate_slots uses date.weekday().
"""
from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple
import uuid
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.route import Route
from app.models.time_entry import TimeEntry
from app.schemas.ops import WeeklyPlanImportRequest, WeeklyPlanImportResponse, WeeklyPlanLeg
from app.services.settings_service import get_usd_to_tzs_rate


# Location code -> display label (used in routes and UI)
LOCATION_ALIAS = {
    "JNIA": "Dar es Salaam Airport",
    "DAR": "Dar es Salaam Airport",
    "AAKI": "Zanzibar Airport",
    "ZNZ": "Zanzibar Airport",
    "Nungwi": "Zanzibar Nungwi",
    "Paje": "Paje",  # match seed ROUTES which use "Paje" as label
    "Seacliff": "Zanzibar Seacliff",
    "Zanzibar Seacliff": "Zanzibar Seacliff",
    "Zanzibar Paje": "Zanzibar Paje",
    "Zanzibar Nungwi": "Zanzibar Nungwi",
    "Zanzibar Airport": "Zanzibar Airport",
    "Dar es Salaam Airport": "Dar es Salaam Airport",
}

LABELS_DAR_ES_SALAAM = ["Dar es Salaam Airport"]
LABELS_ZANZIBAR = [
    "Zanzibar Airport",
    "Zanzibar Nungwi",
    "Zanzibar Seacliff",
    "Zanzibar Paje",
    "Paje",  # seed uses "Paje" as to_label in some routes
]


def _resolve_label(code: str) -> Optional[str]:
    """Resolve location code to canonical label."""
    if not code:
        return None
    code = (code or "").strip()
    return LOCATION_ALIAS.get(code) or (code if code in LOCATION_ALIAS.values() else None)


def get_main_region_for_label(label: str) -> str:
    """Return DAR or ZANZIBAR for route classification."""
    if not label:
        return "MAINLAND"
    if label in LABELS_DAR_ES_SALAAM:
        return "DAR"
    if label in LABELS_ZANZIBAR:
        return "ZANZIBAR"
    if "Dar es Salaam" in (label or ""):
        return "DAR"
    if "Zanzibar" in (label or ""):
        return "ZANZIBAR"
    return "MAINLAND"


def get_or_create_route(
    db: Session, from_label: str, to_label: str
) -> Tuple[Optional[Route], bool]:
    """Get existing route or create one. Returns (route, created)."""
    r = (
        db.query(Route)
        .filter(
            Route.from_label == from_label,
            Route.to_label == to_label,
        )
        .first()
    )
    if r:
        return r, False
    r = Route(
        id=str(uuid.uuid4()),
        from_label=from_label,
        to_label=to_label,
        region="Tanzania",
        main_region=get_main_region_for_label(from_label),
    )
    db.add(r)
    db.flush()
    return r, True


# 5H-FSA preset (0=Mon..6=Sun per schema). Transport legs only; scenic (same-place) legs removed.
DEFAULT_PLAN_5H_FSA_LEGS = [
    # Monday: transport JNIA→AAKI, transport AAKI→JNIA
    {"day_of_week": 0, "from_code": "JNIA", "to_code": "AAKI", "start": "09:30", "end": "10:10", "duration_minutes": 40},
    {"day_of_week": 0, "from_code": "AAKI", "to_code": "JNIA", "start": "13:40", "end": "14:20", "duration_minutes": 40},
    # Friday: JNIA→AAKI, AAKI→Nungwi, Nungwi→Seacliff, Seacliff→AAKI, AAKI→JNIA
    {"day_of_week": 4, "from_code": "JNIA", "to_code": "AAKI", "start": "12:00", "end": "12:40", "duration_minutes": 40},
    {"day_of_week": 4, "from_code": "AAKI", "to_code": "Nungwi", "start": "13:00", "end": "13:30", "duration_minutes": 30},
    {"day_of_week": 4, "from_code": "Nungwi", "to_code": "Seacliff", "start": "15:35", "end": "16:25", "duration_minutes": 50},
    {"day_of_week": 4, "from_code": "Seacliff", "to_code": "AAKI", "start": "16:40", "end": "17:20", "duration_minutes": 40},
    {"day_of_week": 4, "from_code": "AAKI", "to_code": "JNIA", "start": "17:40", "end": "18:20", "duration_minutes": 40},
    # Saturday: JNIA→Seacliff, transfer Seacliff→AAKI
    {"day_of_week": 5, "from_code": "JNIA", "to_code": "Seacliff", "start": "11:10", "end": "11:25", "duration_minutes": 15},
    {"day_of_week": 5, "from_code": "Seacliff", "to_code": "AAKI", "start": "12:50", "end": "13:30", "duration_minutes": 40},
    # Sunday: AAKI→Paje, Paje→Nungwi, Nungwi→JNIA
    {"day_of_week": 6, "from_code": "AAKI", "to_code": "Paje", "start": "14:25", "end": "14:50", "duration_minutes": 25},
    {"day_of_week": 6, "from_code": "Paje", "to_code": "Nungwi", "start": "15:40", "end": "16:05", "duration_minutes": 25},
    {"day_of_week": 6, "from_code": "Nungwi", "to_code": "JNIA", "start": "17:35", "end": "18:35", "duration_minutes": 60},
]

PRESETS = ["5H-FSA"]


def _leg_to_namespace(leg: dict) -> SimpleNamespace:
    return SimpleNamespace(
        day_of_week=leg["day_of_week"],
        from_code=leg["from_code"],
        to_code=leg["to_code"],
        start=leg["start"],
        end=leg["end"],
        duration_minutes=leg["duration_minutes"],
    )


def get_preset_legs(plan_id: str) -> List[SimpleNamespace]:
    """Return list of leg-like objects for preset (0=Mon..6=Sun)."""
    if plan_id == "5H-FSA":
        return [_leg_to_namespace(leg) for leg in DEFAULT_PLAN_5H_FSA_LEGS]
    return []


def _end_time(start_hhmm: str, dur_min: int) -> str:
    hh, mm = map(int, start_hhmm.split(":"))
    total = hh * 60 + mm + dur_min
    total %= 1440
    eh, em = divmod(total, 60)
    return f"{eh:02d}:{em:02d}"


def import_weekly_plan(db: Session, body: WeeklyPlanImportRequest) -> WeeklyPlanImportResponse:
    """
    Create routes (if needed) and time entries for the given week.
    week_start_date is Monday (YYYY-MM-DD). day_of_week in legs: 0=Mon .. 6=Sun.
    """
    routes_created = 0
    time_entries_created = 0
    errors: List[str] = []

    try:
        year, month, day = map(int, body.week_start_date.split("-"))
        week_start = date(year, month, day)
    except (ValueError, TypeError):
        errors.append("Invalid week_start_date")
        return WeeklyPlanImportResponse(routes_created=0, time_entries_created=0, errors=errors)

    legs: List[WeeklyPlanLeg] = body.legs if body.legs else []
    if not legs and body.plan_id:
        for leg_dict in DEFAULT_PLAN_5H_FSA_LEGS:
            legs.append(
                WeeklyPlanLeg(
                    day_of_week=leg_dict["day_of_week"],
                    from_code=leg_dict["from_code"],
                    to_code=leg_dict["to_code"],
                    start=leg_dict["start"],
                    end=leg_dict["end"],
                    duration_minutes=leg_dict["duration_minutes"],
                )
            )

    tzs_rate = get_usd_to_tzs_rate(db)
    price_tzs = body.default_price_usd * tzs_rate

    for leg in legs:
        from_label = _resolve_label(leg.from_code)
        to_label = _resolve_label(leg.to_code)
        if not from_label:
            from_label = leg.from_code
        if not to_label:
            to_label = leg.to_code
        if not from_label or not to_label:
            errors.append(f"Unknown code: {leg.from_code} or {leg.to_code}")
            continue

        route, created = get_or_create_route(db, from_label, to_label)
        if created:
            routes_created += 1
        if not route:
            continue

        # date for this leg: Monday + day_of_week (0=Mon .. 6=Sun)
        leg_date = week_start + timedelta(days=leg.day_of_week)
        date_str = leg_date.isoformat()
        end_time = _end_time(leg.start, leg.duration_minutes)

        existing = (
            db.query(TimeEntry)
            .filter_by(route_id=route.id, date_str=date_str, start=leg.start)
            .first()
        )
        if existing:
            continue

        db.add(
            TimeEntry(
                id=str(uuid.uuid4()),
                route_id=route.id,
                date_str=date_str,
                start=leg.start,
                end=end_time,
                price_usd=body.default_price_usd,
                price_tzs=price_tzs,
                seats_available=body.default_capacity,
                flight_no=f"{body.flight_no_prefix}{leg_date.strftime('%m%d')}",
                cabin="Economy",
            )
        )
        time_entries_created += 1

    return WeeklyPlanImportResponse(
        routes_created=routes_created,
        time_entries_created=time_entries_created,
        errors=errors if errors else [],
    )
