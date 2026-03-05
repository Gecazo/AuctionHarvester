# AuctionHarvester

Multi-region WoW auction tracker with parallel downloads and automatic 3-tier data aggregation.

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 setup_credentials.py
docker compose up -d
python3 init_postgres.py
```

## Usage

**Download one realm:**
```bash
python3 download_realm_auctions.py --region eu --realm kazzak
```

**Download all realms in a region:**
```bash
python3 download_realm_auctions.py --region eu --all
```

**Store in PostgreSQL:**
```bash
python3 ingest_auctions_to_postgres.py
```

**Run continuous updates (all regions, every 20 minutes):**
```bash
python3 run_updater.py --regions eu,us,kr,tw --interval-minutes 20
```

At midnight UTC, it automatically aggregates yesterday's data into hourly windows and daily averages, then cleans up raw snapshots older than 6 hours.

## Deploy To UGREEN DXP4800

Use the deployment helper to push compose config, sync realm lists, and start containers over SSH:

```bash
./deploy_to_ugreen.sh \
  --host <ugreen-ip> \
  --user <ssh-user> \
  --blizzard-client-id <client-id> \
  --blizzard-client-secret <client-secret>
```

Defaults:
- Image: `dockazo/auctionharvester-updater:latest`
- Remote directory: `~/auctionharvester`
- Regions: `eu,us,kr,tw`
- Interval: `20` minutes

Show all options:

```bash
./deploy_to_ugreen.sh --help
```

## Data Architecture

**Tier 1: Raw snapshots** (6-hour retention)
- Fetched every 20 minutes from Blizzard API
- Tables: `snapshots` + `auctions`

**Tier 2: Windowed aggregates** (indefinite)
- 4 windows per day (morning/day/evening/night): 00:00–06:00, 06:00–12:00, 12:00–18:00, 18:00–24:00 UTC
- Table: `windowed_snapshots_avg`
- Created automatically at midnight UTC

**Tier 3: Daily averages** (indefinite)
- One row per (realm, item, day)
- Table: `daily_snapshots_avg`
- Averages the 4 windows above

**Storage:** ~13 GB total, ~800 MB growth/day (vs 5-6 GB/day before optimization)

**Query examples:**
```sql
-- Last 6 hours (granular)
SELECT * FROM auctions WHERE snapshot_id IN 
  (SELECT id FROM snapshots WHERE fetched_at > NOW() - INTERVAL '6 hours');

-- Hourly windows
SELECT realm_id, item_id, "window", avg_buyout FROM windowed_snapshots_avg WHERE target_date = '2026-03-02';

-- Daily history
SELECT realm_id, item_id, fetched_at, avg_buyout FROM daily_snapshots_avg ORDER BY fetched_at DESC;
```


