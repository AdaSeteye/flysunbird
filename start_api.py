#!/usr/bin/env python3
"""
Run migrations (same process, same DATABASE_URL), then seed, then uvicorn.
Ensures tables exist before seed and app start.
"""
import os
import sys

# 1) Wait for DB
import wait_for_db  # noqa: F401

# 2) Run migrations using the same settings as the app
from app.core.config import settings
from alembic.config import Config
from alembic import command

alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
command.upgrade(alembic_cfg, "head")

# 3) Seed using an engine created *after* migrations (avoids app engine created during Alembic env load)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
seed_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SeedSession = sessionmaker(autocommit=False, autoflush=False, bind=seed_engine)
seed_db = SeedSession()
from app.seed import run as run_seed
run_seed(seed_db)
seed_db.close()
seed_engine.dispose()

# 4) Start uvicorn (replace current process)
os.execv(
    sys.executable,
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
)
