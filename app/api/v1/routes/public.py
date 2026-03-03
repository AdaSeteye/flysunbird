from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.route import Route
from app.models.location import Location
from app.models.time_entry import TimeEntry
from app.schemas.ops_payload import PublicRouteOut
from app.services.ops_payload_service import build_ops_payload, to_ops_b64url
from app.services.settings_service import get_usd_to_tzs_rate

router = APIRouter(tags=["public"])


def _normalize_from_label(from_label: str) -> str:
    """Map customer-facing origin names to route from_label (e.g. Nungwi -> Zanzibar Nungwi)."""
    t = (from_label or "").strip()
    if t.lower() == "nungwi":
        return "Zanzibar Nungwi"
    return t


def _dar_es_salaam_airport_excluded_weekdays():
    """Weekdays when no flights originate from Dar es Salaam Airport (Tuesday=1, Sunday=6)."""
    return (1, 6)  # Tuesday, Sunday


@router.get("/public/fx-rate")
def get_public_fx_rate(db: Session = Depends(get_db)):
    """Public TZS per USD rate for customer-facing price display."""
    return {"usdToTzs": get_usd_to_tzs_rate(db)}


def _time_entry_price_usd(t) -> int:
    if getattr(t, "override_price_usd", None) not in (None, 0):
        return t.override_price_usd
    if getattr(t, "base_price_usd", 0) not in (0, None):
        return t.base_price_usd
    return t.price_usd

@router.get("/public/origins")
def list_origins(db: Session = Depends(get_db)):
    """List booking origins from Service Locations. Only "Name Sub" per sub; bare name only when no location with that name has subs (so Dar es Salaam never appears if Dar es Salaam Airport exists)."""
    locations = db.query(Location).filter(Location.active == True).order_by(Location.region.asc(), Location.name.asc()).all()
    # Names that have at least one sub anywhere: do not show bare name for these
    names_that_have_subs = set()
    for loc in locations:
        name = (loc.name or "").strip()
        subs = loc.subs
        if name and subs:
            names_that_have_subs.add(name)
    origins = []
    seen = set()
    for loc in locations:
        name = (loc.name or "").strip()
        subs = loc.subs
        region_raw = (loc.region or "").lower()
        if "zanzibar" in region_raw or (name and "zanzibar" in name.lower()):
            region_group = "ZANZIBAR"
        elif "other" in region_raw or (name and "other" in name.lower()):
            region_group = "OTHER"
        else:
            region_group = "DAR"
        if not name:
            continue
        if subs:
            labels = [f"{name} {sub}".strip() for sub in subs if (f"{name} {sub}".strip())]
        else:
            # No subs: only add bare name if no other location with this name has subs
            if name in names_that_have_subs:
                continue
            labels = [name]
        for label in labels:
            if not label or label in seen:
                continue
            seen.add(label)
            origins.append({"label": label, "region": region_group})
    return {"origins": origins}


@router.get("/public/routes", response_model=list[PublicRouteOut])
def list_routes(db: Session = Depends(get_db)):
    """List active routes. Use the returned `id` as `route_id` for ops-link and time-entries."""
    items = db.query(Route).filter(Route.active == True).all()
    return [
        PublicRouteOut(
            id=str(r.id),
            from_=str(r.from_label),
            to=str(r.to_label),
            region=str(r.region or "Tanzania"),
            mainRegion=str(getattr(r, "main_region", None) or "MAINLAND"),
            subRegion=str(getattr(r, "sub_region", None)) if getattr(r, "sub_region", None) is not None else None,
        )
        for r in items
    ]

@router.get("/public/ops-payload")
def get_ops_payload(route_id: str, dateStr: str, currency: str = "USD", db: Session = Depends(get_db)):
    try:
        payload = build_ops_payload(db, route_id=route_id, date_str=dateStr, currency=currency)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/public/ops-link")
def get_ops_link(route_id: str, dateStr: str, currency: str = "USD", db: Session = Depends(get_db)):
    try:
        payload = build_ops_payload(db, route_id=route_id, date_str=dateStr, currency=currency)
        return {"opsParam": to_ops_b64url(payload)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/public/calendar-availability")
def calendar_availability(
    from_label: str,
    start: str,
    end: str,
    pax: int = 1,
    db: Session = Depends(get_db),
):
    """Return per-date min price and availability for the calendar. Only dates with at least one slot (seats_available >= pax) are included."""
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="start and end must be YYYY-MM-DD")
    if start_dt > end_dt or (end_dt - start_dt).days > 365:
        raise HTTPException(status_code=400, detail="Invalid date range")
    pax = max(1, min(99, pax))

    from_trim = _normalize_from_label(from_label)
    routes = db.query(Route.id).filter(
        Route.active == True,
        func.lower(Route.from_label) == from_trim.lower(),
    ).all()
    route_ids = [r.id for r in routes]
    if not route_ids:
        return {}

    out = {}
    current = start_dt
    while current <= end_dt:
        date_str = current.strftime("%Y-%m-%d")
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.route_id.in_(route_ids),
                TimeEntry.date_str == date_str,
                TimeEntry.visibility == "PUBLIC",
                TimeEntry.status == "PUBLISHED",
                TimeEntry.seats_available >= pax,
            )
            .all()
        )
        if entries:
            # Dar es Salaam Airport: no flights on Tuesday or Sunday
            if from_trim.lower() == "dar es salaam airport":
                wd = current.weekday()
                if wd in _dar_es_salaam_airport_excluded_weekdays():
                    pass  # do not add this date
                else:
                    min_usd = min(_time_entry_price_usd(t) for t in entries)
                    out[date_str] = {"minPriceUSD": min_usd}
            else:
                min_usd = min(_time_entry_price_usd(t) for t in entries)
                out[date_str] = {"minPriceUSD": min_usd}
        current += timedelta(days=1)
    return out


@router.get("/public/slot-dates")
def list_dates_with_slots(
    from_label: str,
    db: Session = Depends(get_db),
):
    """Return dates that have at least one slot (time entry) for the given origin. Useful to see which dates are currently in the DB."""
    from_trim = _normalize_from_label(from_label)
    routes = db.query(Route.id).filter(
        Route.active == True,
        func.lower(Route.from_label) == from_trim.lower(),
    ).all()
    route_ids = [r.id for r in routes]
    if not route_ids:
        return {"from_label": from_trim, "dates": []}
    rows = (
        db.query(TimeEntry.date_str)
        .filter(
            TimeEntry.route_id.in_(route_ids),
            TimeEntry.visibility == "PUBLIC",
            TimeEntry.status == "PUBLISHED",
            TimeEntry.seats_available > 0,
        )
        .distinct()
        .order_by(TimeEntry.date_str.asc())
        .all()
    )
    dates = [r[0] for r in rows]
    # Apply same rules as calendar: Dar es Salaam Airport has no flights on Tuesday or Sunday
    if from_trim.lower() == "dar es salaam airport":
        excluded = _dar_es_salaam_airport_excluded_weekdays()
        dates = [
            d for d in dates
            if datetime.strptime(d, "%Y-%m-%d").date().weekday() not in excluded
        ]
    return {"from_label": from_trim, "dates": dates}


@router.get("/public/time-entries")
def list_time_entries(
    dateStr: str,
    route_id: Optional[str] = None,
    from_label: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List slots for a date. Provide either route_id or from_label (origin); from_label returns slots from all routes with that origin."""
    if route_id:
        route_ids = [route_id]
    elif from_label:
        from_trim = _normalize_from_label(from_label)
        # Dar es Salaam Airport: no flights on Tuesday or Sunday
        if from_trim.lower() == "dar es salaam airport":
            try:
                dt = datetime.strptime(dateStr, "%Y-%m-%d").date()
                if dt.weekday() in _dar_es_salaam_airport_excluded_weekdays():
                    return {"items": []}
            except ValueError:
                pass
        routes = db.query(Route.id).filter(
            Route.active == True,
            func.lower(Route.from_label) == from_trim.lower(),
        ).all()
        route_ids = [r.id for r in routes]
        if not route_ids:
            return {"items": []}
    else:
        raise HTTPException(status_code=400, detail="Provide route_id or from_label")

    q = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.route_id.in_(route_ids),
            TimeEntry.date_str == dateStr,
            TimeEntry.visibility == "PUBLIC",
            TimeEntry.status == "PUBLISHED",
            TimeEntry.seats_available > 0,
        )
        .order_by(TimeEntry.start.asc())
        .all()
    )
    items_out = []
    for t in q:
        route = db.get(Route, t.route_id) if t.route_id else None
        item = {
            "id": t.id,
            "start": t.start,
            "end": t.end,
            "priceUSD": _time_entry_price_usd(t),
            "priceTZS": (
                t.override_price_tzs
                if getattr(t, "override_price_tzs", None) not in (None, 0)
                else (t.base_price_tzs if getattr(t, "base_price_tzs", None) is not None else (t.price_tzs if t.price_tzs is not None else None))
            ),
            "seatsAvailable": t.seats_available,
            "flightNo": t.flight_no,
            "cabin": t.cabin,
        }
        if route:
            item["from_label"] = route.from_label
            item["to_label"] = route.to_label
        items_out.append(item)
    return {"items": items_out}
