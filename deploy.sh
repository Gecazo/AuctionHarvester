#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy AuctionHarvester to a remote UGREEN server over SSH.

Required:
  --host HOST                  Remote host or IP
  --user USER                  SSH username
  --blizzard-client-id ID      Blizzard API client ID
  --blizzard-client-secret SEC Blizzard API client secret

Optional:
  --port PORT                  SSH port (default: 22)
  --remote-dir DIR             Remote deploy directory (default: ~/auctionharvester)
  --image IMAGE                Updater image (default: dockazo/auctionharvester-updater:latest)
  --regions LIST               Regions list (default: eu,us,kr,tw)
  --interval-minutes N         Update interval in minutes (default: 20)

Example:
  ./deploy_to_ugreen.sh \
    --host 192.168.1.50 \
    --user admin \
    --blizzard-client-id abc123 \
    --blizzard-client-secret supersecret
USAGE
}

HOST=""
USER_NAME=""
PORT="22"
REMOTE_DIR="~/auctionharvester"
IMAGE="dockazo/auctionharvester-updater:latest"
REGIONS="eu,us,kr,tw"
INTERVAL_MINUTES="20"
BLIZZARD_CLIENT_ID=""
BLIZZARD_CLIENT_SECRET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="${2:-}"
      shift 2
      ;;
    --image)
      IMAGE="${2:-}"
      shift 2
      ;;
    --regions)
      REGIONS="${2:-}"
      shift 2
      ;;
    --interval-minutes)
      INTERVAL_MINUTES="${2:-}"
      shift 2
      ;;
    --blizzard-client-id)
      BLIZZARD_CLIENT_ID="${2:-}"
      shift 2
      ;;
    --blizzard-client-secret)
      BLIZZARD_CLIENT_SECRET="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" || -z "$USER_NAME" || -z "$BLIZZARD_CLIENT_ID" || -z "$BLIZZARD_CLIENT_SECRET" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 1
fi

SSH_TARGET="$USER_NAME@$HOST"
SSH_OPTS=(-p "$PORT")
SCP_OPTS=(-P "$PORT")
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[1/5] Preparing remote directories..."
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p $REMOTE_DIR/{data,pgdata,realm_lists}"

echo "[2/4] Writing remote .env..."
ENV_FILE="$TMP_DIR/.env"
{
  printf 'BLIZZARD_CLIENT_ID=%s\n' "$BLIZZARD_CLIENT_ID"
  printf 'BLIZZARD_CLIENT_SECRET=%s\n' "$BLIZZARD_CLIENT_SECRET"
  printf 'REGIONS=%s\n' "$REGIONS"
  printf 'INTERVAL_MINUTES=%s\n' "$INTERVAL_MINUTES"
  printf 'OUTPUT_DIR=data\n'
  printf 'POSTGRES_DATA_PATH=./pgdata\n'
  printf 'AUCTION_DATA_PATH=./data\n'
  printf 'REALM_LISTS_PATH=./realm_lists\n'
} > "$ENV_FILE"
scp "${SCP_OPTS[@]}" "$ENV_FILE" "$SSH_TARGET:$REMOTE_DIR/.env"

echo "[3/4] Writing remote docker-compose.yml..."
COMPOSE_FILE="$TMP_DIR/docker-compose.yml"
cat > "$COMPOSE_FILE" <<'EOF'
services:
  postgres:
    image: postgres:16
    container_name: auctionharvester-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: auction
      POSTGRES_PASSWORD: auction
      POSTGRES_DB: auctionharvester
      POSTGRES_INITDB_ARGS: "-c shared_buffers=128MB -c effective_cache_size=256MB -c work_mem=16MB -c maintenance_work_mem=32MB -c random_page_cost=1.1"
    ports:
      - "5432:5432"
    volumes:
      - ${POSTGRES_DATA_PATH}:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U auction -d auctionharvester"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s


  updater:
    image: __UPDATER_IMAGE__
    container_name: auctionharvester-updater
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://auction:auction@postgres:5432/auctionharvester
      BLIZZARD_CLIENT_ID: ${BLIZZARD_CLIENT_ID}
      BLIZZARD_CLIENT_SECRET: ${BLIZZARD_CLIENT_SECRET}
      REGIONS: ${REGIONS}
      INTERVAL_MINUTES: ${INTERVAL_MINUTES}
      OUTPUT_DIR: ${OUTPUT_DIR}
    volumes:
      - ${AUCTION_DATA_PATH}:/app/data
      - ${REALM_LISTS_PATH}:/app/realm_lists:ro
EOF
sed -i '' "s|__UPDATER_IMAGE__|$IMAGE|g" "$COMPOSE_FILE"
scp "${SCP_OPTS[@]}" "$COMPOSE_FILE" "$SSH_TARGET:$REMOTE_DIR/docker-compose.yml"

echo "[4/4] Pulling image and starting services..."
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "cd $REMOTE_DIR && docker compose pull && docker compose up -d && docker compose ps"

echo
echo "Deployment complete."
echo "Follow logs with: ssh -p $PORT $SSH_TARGET 'cd $REMOTE_DIR && docker compose logs -f updater'"
