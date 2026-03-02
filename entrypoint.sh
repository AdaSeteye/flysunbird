#!/bin/sh
set -e
cd /app
echo "[entrypoint] FlySunbird API entrypoint (migrations + seed then start)"

# Wait for Postgres
echo "[entrypoint] Waiting for database..."
python wait_for_db.py

# Run migrations so tables always exist (use python -m so app env/settings are loaded)
echo "[entrypoint] Running migrations..."
python -m alembic upgrade head
if [ $? -ne 0 ]; then
  echo "[entrypoint] ERROR: alembic upgrade failed"
  exit 1
fi

# Seed (route, slot rule, users, settings) using a fresh engine after migrations
echo "[entrypoint] Seeding..."
python -c "
from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.seed import run as run_seed
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
try:
    run_seed(session)
finally:
    session.close()
    engine.dispose()
"

# Slots are filled day-by-day by Ops via admin (Fill slots). No automatic generation.
# Optional: set CLEAN_UNUSED_SLOTS_ON_START=1 to delete all slots that have no bookings (e.g. to clear leftover slots from before). Unset after one run.

if [ -n "$CLEAN_UNUSED_SLOTS_ON_START" ] && [ "$CLEAN_UNUSED_SLOTS_ON_START" = "1" ]; then
  echo "[entrypoint] Cleaning unused slots (no bookings)..."
  python -c "
from app.core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = Session()
try:
    r = db.execute(text(\"DELETE FROM time_entries WHERE id NOT IN (SELECT time_entry_id FROM bookings WHERE time_entry_id IS NOT NULL)\"))
    db.commit()
    print('[entrypoint] Cleaned', r.rowcount, 'unused slot(s)')
except Exception as e:
    db.rollback()
    print('[entrypoint] Clean unused slots warning:', e)
finally:
    db.close()
    engine.dispose()
"
fi

# Remove legacy unused slots on specific dates only (Sat Feb 28, Mon Mar 9, Mon Mar 16, Mon Mar 30, Mon Apr 6)
echo "[entrypoint] Removing legacy unused slots on known dates..."
python -c "
from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.booking import Booking
from app.models.time_entry import TimeEntry
LEGACY_DATES = [
    '2024-02-28', '2024-03-09', '2024-03-16', '2024-03-30', '2024-04-06',
    '2025-02-28', '2025-03-09', '2025-03-16', '2025-03-30', '2025-04-06',
]
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = Session()
try:
    used_ids = {r[0] for r in db.query(Booking.time_entry_id).filter(Booking.time_entry_id.isnot(None)).distinct().all()}
    q = db.query(TimeEntry).filter(TimeEntry.date_str.in_(LEGACY_DATES))
    if used_ids:
        q = q.filter(~TimeEntry.id.in_(used_ids))
    to_delete = q.all()
    for te in to_delete:
        db.delete(te)
    db.commit()
    print('[entrypoint] Removed', len(to_delete), 'legacy slot(s) on', LEGACY_DATES)
except Exception as e:
    db.rollback()
    print('[entrypoint] Cleanup legacy slots warning:', e)
finally:
    db.close()
    engine.dispose()
"

echo "[entrypoint] Starting application..."
exec "$@"
