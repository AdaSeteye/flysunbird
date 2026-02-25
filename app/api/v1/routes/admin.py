import uuid
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.api.deps import require_roles
from app.models.user import User
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.cancellation import Cancellation
from app.models.route import Route
from app.models.time_entry import TimeEntry
from app.models.slot_rule import SlotRule
from app.models.setting import Setting
from app.core.security import hash_password
from app.services.audit_service import log_audit
from app.services.email_service import queue_email

router = APIRouter(tags=["admin"])

@router.get("/admin/users")
def list_users(role: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0,
               db: Session = Depends(get_db),
               me: User = Depends(require_roles("admin","superadmin"))):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(func.lower(User.email).like(ql) | func.lower(User.full_name).like(ql))
    total = query.count()
    users = query.order_by(User.created_at.desc()).limit(min(limit,200)).offset(max(offset,0)).all()
    return {
        "total": total,
        "items": [{"id":u.id,"email":u.email,"fullName":u.full_name,"role":u.role,"isActive":u.is_active,"createdAt":u.created_at.isoformat()} for u in users]
    }

@router.post("/admin/users")
def create_user(email: str, fullName: str = "", role: str = "ops", tempPassword: str | None = None,
                db: Session = Depends(get_db),
                me: User = Depends(require_roles("admin","superadmin"))):
    email_l = email.strip().lower()
    if not email_l:
        raise HTTPException(status_code=400, detail="email required")
    exists = db.query(User).filter(User.email == email_l).first()
    if exists:
        raise HTTPException(status_code=409, detail="email already exists")
    if role not in ("ops","admin","finance","pilot","superadmin"):
        raise HTTPException(status_code=400, detail="invalid role")
    pw = tempPassword or (uuid.uuid4().hex[:10] + "A1!")
    u = User(
        id=str(uuid.uuid4()),
        email=email_l,
        full_name=fullName or "",
        role=role,
        password_hash=hash_password(pw),
        is_active=True,
    )
    db.add(u)
    db.commit()
    log_audit(db, actor_user_id=me.email, action="user_created", entity_type="user", entity_id=u.id, details={"email": u.email, "role": role})
    queue_email(db, u.email, "FlySunbird account created", f"Your FlySunbird account is ready.\nRole: {role}\nTemporary password: {pw}\nPlease login and change it.", "")
    return {"ok": True, "id": u.id, "email": u.email, "tempPassword": pw}

@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, fullName: str | None = None, role: str | None = None, isActive: bool | None = None,
                db: Session = Depends(get_db),
                me: User = Depends(require_roles("admin","superadmin"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    if fullName is not None:
        u.full_name = fullName
    if role is not None:
        if role not in ("customer","ops","admin","finance","pilot","superadmin"):
            raise HTTPException(status_code=400, detail="invalid role")
        u.role = role
    if isActive is not None:
        u.is_active = bool(isActive)
    db.commit()
    log_audit(db, actor_user_id=me.email, action="user_updated", entity_type="user", entity_id=u.id, details={"role": u.role, "isActive": u.is_active})
    return {"ok": True}

@router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: str, tempPassword: str | None = None,
                   db: Session = Depends(get_db),
                   me: User = Depends(require_roles("admin","superadmin"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    pw = tempPassword or (uuid.uuid4().hex[:10] + "A1!")
    u.password_hash = hash_password(pw)
    db.commit()
    log_audit(db, actor_user_id=me.email, action="password_reset", entity_type="user", entity_id=u.id, details={"email": u.email})
    queue_email(db, u.email, "FlySunbird password reset", f"Your password was reset.\nTemporary password: {pw}\nPlease change it after login.", "")
    return {"ok": True, "tempPassword": pw}

@router.get("/admin/metrics/overview")
def metrics_overview(fromDate: str | None = None, toDate: str | None = None,
                     db: Session = Depends(get_db),
                     me: User = Depends(require_roles("admin","finance","superadmin"))):
    # dateStr is stored on time_entries; for quick metrics we use booking.created_at day boundaries
    q = db.query(Booking)
    if fromDate:
        q = q.filter(Booking.created_at >= fromDate + "T00:00:00")
    if toDate:
        q = q.filter(Booking.created_at <= toDate + "T23:59:59")
    total_bookings = q.count()
    paid_bookings = q.filter(Booking.payment_status == "paid").count()
    canceled = q.filter(Booking.status.in_(["CANCELED","REFUNDED"])).count()

    revenue = (
        db.query(func.coalesce(func.sum(Payment.amount_usd), 0))
        .select_from(Payment)
        .join(Booking, Booking.id == Payment.booking_id)
        .filter(Payment.status == "paid")
        .scalar()
    )

    return {
        "totalBookings": int(total_bookings),
        "paidBookings": int(paid_bookings),
        "canceledBookings": int(canceled),
        "revenueUSD": int(revenue or 0),
    }

@router.get("/admin/metrics/bookings-per-day")
def bookings_per_day(days: int = 30,
                     db: Session = Depends(get_db),
                     me: User = Depends(require_roles("admin","finance","superadmin"))):
    # group by date(booking.created_at)
    rows = (
        db.query(func.date(Booking.created_at).label("d"), func.count(Booking.id))
        .group_by(func.date(Booking.created_at))
        .order_by(func.date(Booking.created_at).desc())
        .limit(min(days, 180))
        .all()
    )
    rows = [{"date": str(r[0]), "count": int(r[1])} for r in reversed(rows)]
    return {"items": rows}


# -------------------------
# ADMIN: ROUTES + INVENTORY OVERVIEW
# -------------------------
@router.get("/admin/routes")
def admin_list_routes(db: Session = Depends(get_db), me: User = Depends(require_roles("admin","superadmin"))):
    items = db.query(Route).order_by(Route.created_at.desc()).all()
    return [{"id":r.id,"from":r.from_label,"to":r.to_label,"region":r.region,"active":getattr(r,"active",True)} for r in items]

@router.post("/admin/routes")
def admin_create_route(fromLabel: str, toLabel: str, region: str = "Tanzania", active: bool = True,
                       db: Session = Depends(get_db), me: User = Depends(require_roles("admin","superadmin"))):
    r = Route(id=str(uuid.uuid4()), from_label=fromLabel, to_label=toLabel, region=region, active=active)
    db.add(r)
    log_audit(db, me.id, "route.create", "route", r.id, {"from":fromLabel,"to":toLabel,"region":region,"active":active})
    db.commit()
    return {"id": r.id}

@router.delete("/admin/reset/all")
def admin_reset_all(seed: bool = True, db: Session = Depends(get_db), me: User = Depends(require_roles("admin","superadmin"))):
    # same as ops reset
    db.execute("TRUNCATE TABLE email_logs RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE pilot_assignments RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE payments RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE passengers RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE cancellations RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE audit_logs RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE bookings RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE time_entries RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE slot_rules RESTART IDENTITY CASCADE")
    db.execute("TRUNCATE TABLE routes RESTART IDENTITY CASCADE")
    db.commit()
    if seed:
        from app.seed import run as seed_run
        seed_run()
    return {"ok": True, "seeded": seed}
