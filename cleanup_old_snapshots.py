"""
Delete old raw snapshots and their associated auction rows.

The daily_snapshots_avg table stores aggregated data, so raw granular
snapshots only need to be kept long enough for the daily aggregation
to run (which happens at midnight).  Default retention: 2 days.

After deleting rows the script runs VACUUM to reclaim disk space.
"""

import argparse
import logging
import os
import sys

import psycopg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_connection() -> psycopg.Connection:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "auctionharvester")
    db_user = os.getenv("DB_USER", "auction")
    db_password = os.getenv("DB_PASSWORD", "auction")

    conn = psycopg.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )
    logger.info("Connected to database")
    return conn


def delete_old_snapshots(conn: psycopg.Connection, retention_days: int) -> tuple[int, int]:
    """
    Delete snapshots (and cascade-delete their auctions) older than
    retention_days.

    Returns (snapshots_deleted, estimated_auctions_deleted).
    """
    with conn.cursor() as cur:
        # Count what we're about to delete
        cur.execute(
            "SELECT COUNT(*) FROM snapshots WHERE fetched_at < NOW() - INTERVAL '%s days'",
            (retention_days,),
        )
        snapshot_count = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COALESCE(SUM(s.auctions_count), 0)
            FROM snapshots s
            WHERE s.fetched_at < NOW() - INTERVAL '%s days'
            """,
            (retention_days,),
        )
        auction_estimate = cur.fetchone()[0]

        if snapshot_count == 0:
            logger.info("No old snapshots to delete")
            return 0, 0

        logger.info(
            f"Deleting {snapshot_count} snapshots (~{auction_estimate:,} auctions) "
            f"older than {retention_days} days..."
        )

        # Delete in batches to avoid long locks
        total_deleted = 0
        batch_size = 100
        while True:
            cur.execute(
                """
                DELETE FROM snapshots
                WHERE id IN (
                    SELECT id FROM snapshots
                    WHERE fetched_at < NOW() - INTERVAL '%s days'
                    ORDER BY id
                    LIMIT %s
                )
                """,
                (retention_days, batch_size),
            )
            deleted = cur.rowcount
            conn.commit()
            total_deleted += deleted
            if deleted > 0:
                logger.info(f"  Deleted batch: {deleted} snapshots (total: {total_deleted})")
            if deleted < batch_size:
                break

        return total_deleted, auction_estimate


def vacuum_tables(conn: psycopg.Connection) -> None:
    """Run VACUUM on auctions and snapshots to reclaim disk space."""
    logger.info("Running VACUUM on auctions and snapshots tables...")
    # VACUUM cannot run inside a transaction
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("VACUUM VERBOSE auctions")
        cur.execute("VACUUM VERBOSE snapshots")
    conn.autocommit = False
    logger.info("VACUUM completed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete old raw snapshots and reclaim disk space"
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=2,
        help="Keep snapshots from the last N days (default: 2)",
    )
    parser.add_argument(
        "--skip-vacuum",
        action="store_true",
        help="Skip VACUUM after deletion (faster but won't reclaim disk space immediately)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = get_db_connection()

    try:
        snapshots_deleted, auctions_estimate = delete_old_snapshots(
            conn, retention_days=args.retention_days
        )

        if snapshots_deleted > 0:
            logger.info(
                f"Cleanup complete: removed {snapshots_deleted} snapshots "
                f"(~{auctions_estimate:,} auction rows via CASCADE)"
            )
            if not args.skip_vacuum:
                vacuum_tables(conn)
        else:
            logger.info("Nothing to clean up")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
