#!/usr/bin/env bash
set -eu

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os, time, psycopg
url = os.environ["DATABASE_URL"]
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

echo "Initializing database schema..."
python init_postgres.py

echo "Starting updater..."
exec python run_updater.py \
  --regions "${REGIONS:-eu,us,kr,tw}" \
  --interval-minutes "${INTERVAL_MINUTES:-20}" \
  --output-dir "${OUTPUT_DIR:-data}"
