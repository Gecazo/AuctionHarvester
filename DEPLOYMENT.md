# AuctionHarvester Deployment Guide

Multi-region WoW auction tracker that fetches data from the Blizzard API every 20 minutes and stores it in PostgreSQL with automatic 3-tier data aggregation.

## Requirements

- **Docker** and **Docker Compose** 
- **Blizzard API credentials** from [Blizzard Developer Portal](https://develop.battle.net/)
- **SSH access** (for remote server deployment)

## Local Deployment

### 1. Set up Blizzard API credentials

```bash
echo 'BLIZZARD_CLIENT_ID=your_client_id_here' > .env
echo 'BLIZZARD_CLIENT_SECRET=your_client_secret_here' >> .env
```

Replace the placeholder values with your actual Blizzard API credentials from [Blizzard Developer Portal](https://develop.battle.net/).

### 2. Start the application

```bash
docker compose up -d
```

This will:
- Build the updater image (includes realm lists for all 4 regions)
- Start PostgreSQL on port `5433`
- Start the updater service
- Begin fetching auction data every 20 minutes from the Blizzard API

### 3. Monitor logs

```bash
docker compose logs -f updater
```

Expected output:
```
PostgreSQL is ready
Validating realm lists...
Initializing database schema...
Starting updater...
[2026-03-05T22:37:08] Starting update cycle for EU
arthas [1/58] (57 left)
alexstrasza [2/58] (56 left)
...
```

## Configuration

Edit `.env` to customize:

```bash
# Required
BLIZZARD_CLIENT_ID=your_client_id
BLIZZARD_CLIENT_SECRET=your_client_secret

# Optional (defaults shown)
REGIONS=eu,us,kr,tw          # Regions to track
INTERVAL_MINUTES=20          # Update interval in minutes
```

## Remote Server Deployment

### Deploy to your UGREEN server

From your local machine:

```bash
./deploy.sh \
  --host 192.168.1.50 \
  --user admin \
  --blizzard-client-id YOUR_CLIENT_ID \
  --blizzard-client-secret YOUR_CLIENT_SECRET
```

**Important:** Credentials must be passed as arguments to the deploy script. If missing, the container will fail to start.

**Optional parameters:**
```bash
  --port 22                              # SSH port
  --remote-dir ~/auctionharvester        # Remote directory
  --regions eu,us,kr,tw                  # Regions to track
  --interval-minutes 20                  # Update interval
```

The script will:
1. Create remote directories
2. Push the `.env` file with your credentials
3. Push the `docker-compose.yml` configuration
4. Pull the latest Docker image from Docker Hub
5. Start the containers

### Verify deployment

```bash
ssh admin@192.168.1.50
cd ~/auctionharvester
docker compose ps
docker compose logs -f updater
```

## Stopping and Cleaning Up

### Stop containers

```bash
docker compose down
```

### Remove all data (keep volumes)

```bash
docker compose down --remove-orphans
```

### Remove everything including data

```bash
docker compose down -v
```

## Database Access

### PostgreSQL credentials

- **User:** `auction`
- **Password:** `auction`
- **Database:** `auctionharvester`
- **Port:** `5433`

### Connect locally

```bash
psql postgresql://auction:auction@localhost:5433/auctionharvester
```

### Connect via SSH tunnel (remote server)

```bash
ssh -L 5433:localhost:5433 admin@192.168.1.50
psql postgresql://auction:auction@localhost:5433/auctionharvester
```

### Sample queries

```sql
-- Latest auction data for an item
SELECT realm_id, item_id, avg(buyout), count(*)
FROM auctions
WHERE item_id = 123
GROUP BY realm_id, item_id;

-- Daily price history
SELECT target_date, realm_id, item_id, avg_buyout
FROM daily_snapshots_avg
WHERE item_id = 123
ORDER BY target_date DESC
LIMIT 30;

-- Recent snapshots
SELECT * FROM snapshots ORDER BY fetched_at DESC LIMIT 10;
```

## Data Storage

The application uses three storage tiers to optimize space:

1. **Raw snapshots** (6-hour retention)
   - Fetched every 20 minutes
   - Automatically cleaned up

2. **Windowed averages** (indefinite)
   - 4 windows per day (00-06, 06-12, 12-18, 18-24 UTC)
   - Auto-generated at midnight UTC

3. **Daily averages** (indefinite)
   - One row per (realm, item, day)
   - Long-term trend tracking

**Storage savings:** ~800 MB/day vs 5-6 GB/day without aggregation

## Updating the Application

### Pull latest code and restart

```bash
git pull origin main
docker compose pull
docker compose up -d
```

### Rebuild locally

```bash
docker compose up -d --build
```

## Troubleshooting

### Container keeps restarting

Check logs:
```bash
docker compose logs updater
```

**Common issues:**
- `Missing realm list` — Realm lists should be in the image; run `docker compose pull`
- `PostgreSQL connection refused` — Wait 10+ seconds for DB startup
- `Missing environment variables` — Credentials (BLIZZARD_CLIENT_ID/SECRET) not set in `.env`; updater will fail immediately if not found

### Reset database

```bash
docker compose exec updater python3 init_postgres.py
```

### Clear old data

```bash
docker compose exec updater python3 cleanup_old_snapshots.py
```

### Check container status

```bash
docker compose ps
docker compose logs --tail 50 updater
```

## Architecture

```
Blizzard API (every 20 min)
    ↓
Docker Container (Updater)
    ↓
PostgreSQL Database
    ├─ Raw snapshots (6h)
    ├─ Windowed data (indefinite)
    └─ Daily averages (indefinite)
```

## Support & Logging

The updater logs show:
- Realm processing status: `realm_name [current/total] (remaining left)`
- Connected realm processing: `Connected realm ID [current/total] (remaining left)`
- Any errors or skipped items

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `BLIZZARD_CLIENT_ID` | — | **Required**. API client ID |
| `BLIZZARD_CLIENT_SECRET` | — | **Required**. API client secret |
| `REGIONS` | `eu,us,kr,tw` | Comma-separated regions |
| `INTERVAL_MINUTES` | `20` | Minutes between fetches |
| `DATABASE_URL` | `postgresql://auction:auction@postgres:5432/auctionharvester` | PostgreSQL connection |
| `OUTPUT_DIR` | `data` | Directory for auction snapshots |
