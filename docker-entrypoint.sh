#!/usr/bin/env sh
set -eu

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os
import time
import psycopg

url = os.environ.get("DATABASE_URL", "postgresql://auction:auction@postgres:5432/auctionharvester")
for _ in range(60):
    try:
        with psycopg.connect(url, connect_timeout=5):
            print("PostgreSQL is ready")
            break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("PostgreSQL did not become ready in time")
PY

python init_postgres.py
exec python run_updater.py --regions "${REGIONS:-eu,us,kr,tw}" --interval-minutes "${INTERVAL_MINUTES:-20}" --output-dir "${OUTPUT_DIR:-data}"
