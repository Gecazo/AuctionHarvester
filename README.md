# AuctionHarvester

Simple Blizzard auction downloader for one chosen server.

## 1) Save your credentials

```bash
python3 setup_credentials.py
```

Credentials are saved into `.env` and reused by the scripts.

## 2) Download auctions for one server

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
