import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

import psycopg
from psycopg.types.json import Jsonb

FILE_PATTERN = re.compile(r"auctions_(?P<realm>.+)_(?P<region>us|eu|kr|tw)\.json$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load realm auction JSON files into PostgreSQL")
    parser.add_argument("--glob", default="data/auctions_*_*.json", help="File glob pattern")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    return parser.parse_args()


def parse_file_meta(path: pathlib.Path) -> tuple[str, str]:
    match = FILE_PATTERN.search(path.name)
    if not match:
        raise RuntimeError(f"Unexpected filename format: {path.name}")
    return match.group("realm"), match.group("region")


def to_timestamp(payload: dict) -> dt.datetime | None:
    last_updated = payload.get("last_modified_timestamp")
    if isinstance(last_updated, (int, float)):
        return dt.datetime.fromtimestamp(last_updated / 1000, tz=dt.timezone.utc)

    fallback = payload.get("last_updated_timestamp")
    if isinstance(fallback, (int, float)):
        return dt.datetime.fromtimestamp(fallback / 1000, tz=dt.timezone.utc)

    return None


def upsert_realm(cur: psycopg.Cursor, region: str, realm: str, connected_realm_id: int | None) -> int:
    cur.execute(
        """
        INSERT INTO realms(region, realm_slug, connected_realm_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (region, realm_slug)
        DO UPDATE SET connected_realm_id = COALESCE(EXCLUDED.connected_realm_id, realms.connected_realm_id)
        RETURNING id
        """,
        (region, realm, connected_realm_id),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Could not upsert realm")
    return int(row[0])


def insert_snapshot(cur: psycopg.Cursor, realm_id: int, file_path: str, auctions_count: int, fetched_at: dt.datetime | None) -> int:
    cur.execute(
        """
        INSERT INTO snapshots(realm_id, fetched_at, source_file, auctions_count)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (realm_id, fetched_at, file_path, auctions_count),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Could not create snapshot")
    return int(row[0])


def insert_auctions(cur: psycopg.Cursor, snapshot_id: int, auctions: list[dict]) -> int:
    rows: list[tuple] = []
    for idx, auction in enumerate(auctions, start=1):
        auction_id = int(auction.get("id") or idx)
        item_id = auction.get("item", {}).get("id")
        quantity = auction.get("quantity")
        bid = auction.get("bid")
        buyout = auction.get("buyout")
        unit_price = auction.get("unit_price")
        time_left = auction.get("time_left")

        rows.append(
            (
                snapshot_id,
                auction_id,
                item_id,
                quantity,
                bid,
                buyout,
                unit_price,
                time_left,
                Jsonb(auction),
            )
        )

    cur.executemany(
        """
        INSERT INTO auctions(
            snapshot_id, auction_id, item_id, quantity, bid, buyout, unit_price, time_left, raw
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv(
        "DATABASE_URL",
        "postgresql://auction:auction@localhost:5432/auctionharvester",
    )

    files = sorted(pathlib.Path().glob(args.glob))
    if not files:
        print(f"No files matched: {args.glob}", file=sys.stderr)
        raise SystemExit(1)

    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            seen_connected_snapshots: set[tuple[str, int, dt.datetime | None]] = set()
            for path in files:
                realm, region = parse_file_meta(path)
                payload = json.loads(path.read_text(encoding="utf-8"))
                auctions = payload.get("auctions", [])
                if not isinstance(auctions, list):
                    raise RuntimeError(f"Invalid auctions list in {path}")

                connected_realm_id = payload.get("connected_realm", {}).get("id")
                fetched_at = to_timestamp(payload)

                if isinstance(connected_realm_id, int):
                    dedupe_key = (region, connected_realm_id, fetched_at)
                    if dedupe_key in seen_connected_snapshots:
                        print(
                            f"Skipped duplicate connected realm snapshot: {path} "
                            f"(connected_realm_id={connected_realm_id})"
                        )
                        continue
                    seen_connected_snapshots.add(dedupe_key)

                realm_id = upsert_realm(cur, region, realm, connected_realm_id)
                snapshot_id = insert_snapshot(
                    cur,
                    realm_id=realm_id,
                    file_path=str(path),
                    auctions_count=len(auctions),
                    fetched_at=fetched_at,
                )
                inserted = insert_auctions(cur, snapshot_id=snapshot_id, auctions=auctions)
                conn.commit()
                print(f"Inserted {inserted} auctions from {path}")

    print("Done.")


if __name__ == "__main__":
    main()
