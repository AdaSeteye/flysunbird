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

echo "[entrypoint] Starting application..."
exec "$@"
