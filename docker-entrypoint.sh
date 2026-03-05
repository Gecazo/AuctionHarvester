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

echo "Validating realm lists..."
REGIONS_TO_CHECK="${REGIONS:-eu,us,kr,tw}"
for region in $(echo "$REGIONS_TO_CHECK" | tr ',' ' '); do
    region=$(echo "$region" | xargs)
    if [ ! -f "realm_lists/${region}_realms.txt" ]; then
        echo "Missing realm list: realm_lists/${region}_realms.txt" >&2
        echo "Realm generation is disabled at startup." >&2
        echo "Generate manually with: python generate_realm_lists.py --regions $REGIONS_TO_CHECK" >&2
        exit 1
    fi
done

echo "Initializing database schema..."
python init_postgres.py

echo "Starting updater..."
exec python run_updater.py \
  --regions "${REGIONS:-eu,us,kr,tw}" \
  --interval-minutes "${INTERVAL_MINUTES:-20}" \
  --output-dir "${OUTPUT_DIR:-data}"
