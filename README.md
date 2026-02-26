# AuctionHarvester

Simple Blizzard auction downloader for one chosen server.

## Install Python dependency

```bash
python3 -m pip install -r requirements.txt
```

## 1) Save your credentials

```bash
python3 setup_credentials.py
```

Credentials are saved into `.env` and reused by the scripts.

## 2) Option 1: Download one server you choose

Default (Kazzak EU):

```bash
python3 download_realm_auctions.py
```

Choose your own server:

```bash
python3 download_realm_auctions.py --region eu --realm kazzak
```

Examples:

```bash
python3 download_realm_auctions.py --region eu --realm silvermoon
python3 download_realm_auctions.py --region us --realm illidan
```

Output file (auto):

`data/auctions_<realm>_<region>.json`

Optional custom output path:

```bash
python3 download_realm_auctions.py --region eu --realm kazzak --output data/my_kazzak_snapshot.json
```

## 3) Option 2: Update every server in a region

```bash
python3 download_realm_auctions.py --region eu --all
```

Note: `--all` updates the known realm files you already have in `data/`.
Connected realms are deduped under the hood (one API fetch per connected realm),
then written to all linked server files.

Fresh start support:
- The app also checks persisted lists:
	- `realm_lists/eu_realms.txt`
	- `realm_lists/us_realms.txt`
	- `realm_lists/kr_realms.txt`
	- `realm_lists/tw_realms.txt`
- You can pass a custom list file: `--realm-list path/to/list.txt`.

## 4) Store multiple realms in PostgreSQL

Start local PostgreSQL (Docker):

```bash
docker compose up -d
```

Use default DB URL from scripts (`postgresql://auction:auction@localhost:5432/auctionharvester`) or set your own:

```bash
export DATABASE_URL="postgresql://auction:auction@localhost:5432/auctionharvester"
```

Initialize schema:

```bash
python3 init_postgres.py
```

Ingest all downloaded realm files:

```bash
python3 ingest_auctions_to_postgres.py
```

Ingest a custom subset:

```bash
python3 ingest_auctions_to_postgres.py --glob "data/auctions_*_eu.json"
```

## 5) Launch app and update DB every 20 minutes

```bash
. .venv/bin/activate && python run_updater.py --region eu --interval-minutes 20
```

Multiple regions:

```bash
. .venv/bin/activate && python run_updater.py --regions eu,us --interval-minutes 20
```

Run one cycle only:

```bash
. .venv/bin/activate && python run_updater.py --region eu --once
```
