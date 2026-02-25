import os, time
from urllib.parse import urlparse

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL is not set")

# SQLAlchemy URL may start with postgresql+psycopg2://
url = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
p = urlparse(url)

host = p.hostname or "db"
port = p.port or 5432
user = p.username or "flysunbird"
password = p.password or "flysunbird"
dbname = (p.path or "/flysunbird").lstrip("/") or "flysunbird"

timeout_s = int(os.getenv("DB_WAIT_TIMEOUT", "60"))
start = time.time()
last_err = None

print(f"[wait_for_db] Waiting for Postgres at {host}:{port} db={dbname} user={user} (timeout={timeout_s}s)")
while True:
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
        conn.close()
        print("[wait_for_db] Postgres is ready.")
        break
    except Exception as e:
        last_err = e
        if time.time() - start > timeout_s:
            print(f"[wait_for_db] Timed out waiting for DB. Last error: {last_err}")
            raise
        time.sleep(1)
