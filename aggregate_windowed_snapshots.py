"""
Aggregate snapshots into 4 time-of-day windows, then into a daily average.

Windows:
    morning:  00:00-06:00 UTC
    day:      06:00-12:00 UTC
    evening:  12:00-18:00 UTC
    night:    18:00-24:00 UTC

Creates 4 rows per (realm, item) per day instead of millions.
Then optionally averages those 4 into a single daily average.
"""

import logging
import os
import sys
from datetime import datetime, timezone, date, timedelta

import psycopg
from psycopg import sql

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

    try:
        conn = psycopg.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
        )
        logger.info("Connected to database")
        return conn
    except psycopg.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)


def aggregate_window(
    conn: psycopg.Connection,
    target_date: date,
    window: str,
    window_start_hour: int,
    window_end_hour: int,
) -> int:
    """
    Aggregate a 6-hour window into windowed_snapshots_avg table.

    Args:
        conn: PostgreSQL connection
        target_date: Date to aggregate (e.g., March 1)
        window: Window name (morning/day/evening/night)
        window_start_hour: Start hour (0, 6, 12, 18)
        window_end_hour: End hour (6, 12, 18, 24) - 24 = next day midnight

    Returns:
        Number of rows created/updated
    """
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    window_start = day_start.replace(hour=window_start_hour)
    
    # Handle hour 24 (midnight of next day)
    if window_end_hour == 24:
        window_end = (day_start + timedelta(days=1)).replace(hour=0)
    else:
        window_end = day_start.replace(hour=window_end_hour)

    logger.info(f"Aggregating {window} window: {window_start.isoformat()} to {window_end.isoformat()}")

    with conn.cursor() as cur:
        aggregation_query = """
        INSERT INTO windowed_snapshots_avg 
            (realm_id, item_id, target_date, "window", fetched_at, avg_buyout, avg_bid, avg_unit_price, count_auctions)
        SELECT
            s.realm_id,
            a.item_id,
            %s::date AS target_date,
            %s AS "window",
            %s AS fetched_at,
            ROUND(AVG(a.buyout))::BIGINT AS avg_buyout,
            ROUND(AVG(a.bid))::BIGINT AS avg_bid,
            ROUND(AVG(a.unit_price))::BIGINT AS avg_unit_price,
            COUNT(*) AS count_auctions
        FROM snapshots s
        INNER JOIN auctions a ON s.id = a.snapshot_id
        WHERE s.fetched_at >= %s
          AND s.fetched_at < %s
          AND a.item_id IS NOT NULL
        GROUP BY s.realm_id, a.item_id
        ON CONFLICT (realm_id, item_id, target_date, "window") DO UPDATE SET
            avg_buyout = EXCLUDED.avg_buyout,
            avg_bid = EXCLUDED.avg_bid,
            avg_unit_price = EXCLUDED.avg_unit_price,
            count_auctions = EXCLUDED.count_auctions,
            updated_at = NOW()
        """

        try:
            cur.execute(
                aggregation_query,
                (
                    target_date,
                    window,
                    window_end,
                    window_start,
                    window_end,
                ),
            )
            rows_inserted = cur.rowcount
            conn.commit()
            logger.info(f"  {window}: {rows_inserted} rows")
            return rows_inserted
        except psycopg.Error as e:
            conn.rollback()
            logger.error(f"Failed to aggregate {window} window: {e}")
            return 0


def aggregate_daily_from_windows(conn: psycopg.Connection, target_date: date) -> int:
    """
    Aggregate the 4 windows into a single daily average.

    Returns:
        Number of rows created/updated
    """
    logger.info(f"Aggregating daily average from 4 windows for {target_date}")

    with conn.cursor() as cur:
        aggregation_query = """
        INSERT INTO daily_snapshots_avg
            (realm_id, item_id, fetched_at, avg_buyout, avg_bid, avg_unit_price, count_auctions)
        SELECT
            realm_id,
            item_id,
            (%s::date)::timestamp with time zone + interval '23:59:59' AS fetched_at,
            ROUND(AVG(avg_buyout))::BIGINT AS avg_buyout,
            ROUND(AVG(avg_bid))::BIGINT AS avg_bid,
            ROUND(AVG(avg_unit_price))::BIGINT AS avg_unit_price,
            ROUND(AVG(count_auctions))::BIGINT AS count_auctions
        FROM windowed_snapshots_avg
        WHERE target_date = %s
        GROUP BY realm_id, item_id
        ON CONFLICT (realm_id, item_id, fetched_at) DO UPDATE SET
            avg_buyout = EXCLUDED.avg_buyout,
            avg_bid = EXCLUDED.avg_bid,
            avg_unit_price = EXCLUDED.avg_unit_price,
            count_auctions = EXCLUDED.count_auctions,
            updated_at = NOW()
        """

        try:
            cur.execute(aggregation_query, (target_date, target_date))
            rows_inserted = cur.rowcount
            conn.commit()
            logger.info(f"  Daily average: {rows_inserted} rows")
            return rows_inserted
        except psycopg.Error as e:
            conn.rollback()
            logger.error(f"Failed to aggregate daily average: {e}")
            return 0


def delete_old_raw_snapshots(conn: psycopg.Connection, hours_to_keep: int = 6) -> int:
    """
    Delete raw snapshots older than hours_to_keep.

    The windowed_snapshots_avg captures the data, so we can delete raw snapshots
    once they've been aggregated into windows.

    Returns:
        Number of snapshots deleted
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_to_keep)
    logger.info(f"Deleting raw snapshots older than {hours_to_keep} hours ({cutoff_time.isoformat()})")

    with conn.cursor() as cur:
        # Delete in batches to avoid long locks
        total_deleted = 0
        batch_size = 500
        while True:
            cur.execute(
                """
                DELETE FROM snapshots
                WHERE id IN (
                    SELECT id FROM snapshots
                    WHERE fetched_at < %s
                    ORDER BY id
                    LIMIT %s
                )
                """,
                (cutoff_time, batch_size),
            )
            deleted = cur.rowcount
            conn.commit()
            total_deleted += deleted
            if deleted > 0:
                logger.info(f"  Deleted batch: {deleted} snapshots (total: {total_deleted})")
            if deleted < batch_size:
                break

        return total_deleted


def main():
    """Aggregate windows for target date and optionally clean up old raw snapshots."""
    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD")
            sys.exit(1)

    conn = get_db_connection()

    try:
        logger.info(f"Aggregating {target_date}")

        # Aggregate 4 windows
        windows = [
            ("morning", 0, 6),
            ("day", 6, 12),
            ("evening", 12, 18),
            ("night", 18, 24),
        ]

        total_windowed = 0
        for window_name, start_hour, end_hour in windows:
            rows = aggregate_window(conn, target_date, window_name, start_hour, end_hour)
            total_windowed += rows

        # Aggregate windows into daily average
        daily_rows = aggregate_daily_from_windows(conn, target_date)

        logger.info(f"Aggregation complete: {total_windowed} windowed rows, {daily_rows} daily average rows")

        # Clean up raw snapshots older than 6 hours
        deleted = delete_old_raw_snapshots(conn, hours_to_keep=6)
        logger.info(f"Cleaned up {deleted} old raw snapshots")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
