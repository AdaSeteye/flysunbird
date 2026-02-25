import base64, json
from sqlalchemy.orm import Session
from app.models.route import Route
from app.models.time_entry import TimeEntry
from app.services.settings_service import get_usd_to_tzs_rate

def build_ops_payload(db: Session, route_id: str, date_str: str, currency: str = "USD") -> dict:
    route = db.get(Route, route_id)
    if not route or not getattr(route,'active', True):
        raise ValueError("route not found")
    q = (
        db.query(TimeEntry)
        .filter(TimeEntry.route_id == route_id, TimeEntry.date_str == date_str, TimeEntry.visibility == "PUBLIC", TimeEntry.status == "PUBLISHED", TimeEntry.seats_available > 0)
        .order_by(TimeEntry.start.asc())
        .all()
    )
    slots = [{
        "id": r.id,
        "start": r.start,
        "end": r.end,
        "priceUSD": int((getattr(r,"override_price_usd",None) or 0) or (getattr(r,"base_price_usd",0) or 0) or int(r.price_usd)),
        "priceTZS": int((getattr(r,"override_price_tzs",None) or 0) or (getattr(r,"base_price_tzs",None) or 0) or (int(r.price_tzs) if r.price_tzs is not None else int(((getattr(r,"override_price_usd",None) or 0) or (getattr(r,"base_price_usd",0) or 0) or int(r.price_usd)) * get_usd_to_tzs_rate(db)))),
        "seatsAvailable": int(r.seats_available),
        "flightNo": r.flight_no,
        "cabin": r.cabin,
    } for r in q]

    return {
        "from": route.from_label,
        "to": route.to_label,
        "region": route.region,
        "currency": currency,
        "dateStr": date_str,
        "slots": slots,
    }

def to_ops_b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",",":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    return b64
