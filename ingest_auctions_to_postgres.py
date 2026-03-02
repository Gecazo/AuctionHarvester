import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

import psycopg
from tqdm import tqdm

FILE_PATTERN = re.compile(r"auctions_(?P<realm>.+)_(?P<region>us|eu|kr|tw)\.json$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load realm auction JSON files into PostgreSQL")
    parser.add_argument("--glob", default="data/auctions_*_*.json", help="File glob pattern")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    parser.add_argument(
        "--position",
        type=int,
        default=None,
        help="Progress bar position for parallel execution",
    )
    return parser.parse_args()


def parse_file_meta(path: pathlib.Path) -> tuple[str, str]:
    match = FILE_PATTERN.search(path.name)
    if not match:
        raise RuntimeError(f"Unexpected filename format: {path.name}")
    return match.group("realm"), match.group("region")


def to_timestamp(payload: dict, source_path: pathlib.Path) -> dt.datetime:
    last_updated = payload.get("last_modified_timestamp")
    if isinstance(last_updated, (int, float)):
        return dt.datetime.fromtimestamp(last_updated / 1000, tz=dt.timezone.utc)

    fallback = payload.get("last_updated_timestamp")
    if isinstance(fallback, (int, float)):
        return dt.datetime.fromtimestamp(fallback / 1000, tz=dt.timezone.utc)

    file_mtime = source_path.stat().st_mtime
    if isinstance(file_mtime, (int, float)):
        return dt.datetime.fromtimestamp(file_mtime, tz=dt.timezone.utc)

    return dt.datetime.now(tz=dt.timezone.utc)


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


def snapshot_exists(cur: psycopg.Cursor, realm_id: int, fetched_at: dt.datetime) -> bool:
    """Check if a snapshot already exists for this realm at this exact fetched_at time."""
    cur.execute(
        """
        SELECT 1 FROM snapshots
        WHERE realm_id = %s AND fetched_at = %s
        LIMIT 1
        """,
        (realm_id, fetched_at),
    )
    return cur.fetchone() is not None


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
            )
        )

    cur.executemany(
        """
        INSERT INTO auctions(
            snapshot_id, auction_id, item_id, quantity, bid, buyout, unit_price, time_left
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            pbar = tqdm(files, desc="Ingesting auctions", unit="file", position=args.position, leave=True)
            for path in pbar:
                realm, region = parse_file_meta(path)
                payload = json.loads(path.read_text(encoding="utf-8"))
                auctions = payload.get("auctions", [])
                if not isinstance(auctions, list):
                    raise RuntimeError(f"Invalid auctions list in {path}")

                connected_realm_id = payload.get("connected_realm", {}).get("id")
                fetched_at = to_timestamp(payload, source_path=path)

                if isinstance(connected_realm_id, int):
                    dedupe_key = (region, connected_realm_id, fetched_at)
                    if dedupe_key in seen_connected_snapshots:
                        tqdm.write(
                            f"Skipped duplicate: {path.name} "
                            f"(realm_id={connected_realm_id})"
                        )
                        continue
                    seen_connected_snapshots.add(dedupe_key)

                realm_id = upsert_realm(cur, region, realm, connected_realm_id)
                
                # Skip if this exact snapshot already exists in the database
                if snapshot_exists(cur, realm_id, fetched_at):
                    tqdm.write(f"Skipped {path.name}: snapshot already exists")
                    continue
                
                snapshot_id = insert_snapshot(
                    cur,
                    realm_id=realm_id,
                    file_path=str(path),
                    auctions_count=len(auctions),
                    fetched_at=fetched_at,
                )
                inserted = insert_auctions(cur, snapshot_id=snapshot_id, auctions=auctions)
                conn.commit()
                pbar.set_postfix_str(f"{realm}/{region} | {inserted} auctions", refresh=True)

    print("Done.")


if __name__ == "__main__":
    main()
