"""
Aggregates 20-minute granule snapshots into daily average snapshots.
Runs once per day at midnight to aggregate the previous day's data.
Retention: keeps 2 days of historical aggregated data.
"""

import os
import sys
import datetime as dt
import logging
from pathlib import Path

import psycopg
from psycopg import sql

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Connect to PostgreSQL database."""
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


def aggregate_daily_snapshots(conn: psycopg.Connection, target_date: dt.date) -> int:
    """
    Aggregate snapshots for a given day (usually yesterday).
    
    Args:
        conn: PostgreSQL connection
        target_date: Date to aggregate (e.g., March 1 aggregates March 1 data)
    
    Returns:
        Number of daily snapshot rows created
    """
    logger.info(f"Starting aggregation for {target_date}")

    # Define the time range for the target date (in UTC)
    day_start = dt.datetime.combine(target_date, dt.time.min, tzinfo=dt.timezone.utc)
    day_end = dt.datetime.combine(target_date, dt.time.max, tzinfo=dt.timezone.utc)

    with conn.cursor() as cur:
        # Query granular snapshots for the target day and compute aggregates
        aggregation_query = """
        INSERT INTO daily_snapshots_avg 
            (realm_id, item_id, fetched_at, avg_buyout, avg_bid, avg_unit_price, count_auctions)
        SELECT
            s.realm_id,
            a.item_id,
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
        ON CONFLICT (realm_id, item_id, fetched_at) DO UPDATE SET
            avg_buyout = EXCLUDED.avg_buyout,
            avg_bid = EXCLUDED.avg_bid,
            avg_unit_price = EXCLUDED.avg_unit_price,
            count_auctions = EXCLUDED.count_auctions,
            updated_at = NOW()
        """

        # Use end-of-day timestamp as the aggregation timestamp
        fetched_at_timestamp = day_end

        try:
            cur.execute(aggregation_query, (fetched_at_timestamp, day_start, day_end))
            rows_inserted = cur.rowcount
            conn.commit()
            logger.info(f"Inserted/updated {rows_inserted} daily snapshot rows for {target_date}")
            return rows_inserted
        except psycopg.Error as e:
            conn.rollback()
            logger.error(f"Failed to aggregate snapshots: {e}")
            return 0


def delete_old_aggregates(conn: psycopg.Connection, retention_days: int = 2) -> int:
    """
    Delete aggregated snapshots older than the retention period.
    
    Args:
        conn: PostgreSQL connection
        retention_days: Number of days to keep (default: 2)
    
    Returns:
        Number of rows deleted
    """
    cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
    logger.info(f"Deleting daily snapshots older than {cutoff_date}")

    with conn.cursor() as cur:
        delete_query = "DELETE FROM daily_snapshots_avg WHERE fetched_at < %s"
        try:
            cur.execute(delete_query, (cutoff_date,))
            rows_deleted = cur.rowcount
            conn.commit()
            logger.info(f"Deleted {rows_deleted} old daily snapshot rows")
            return rows_deleted
        except psycopg.Error as e:
            conn.rollback()
            logger.error(f"Failed to delete old aggregates: {e}")
            return 0


def main():
    """Main entry point."""
    # By default, aggregate yesterday's data
    target_date = (dt.datetime.now() - dt.timedelta(days=1)).date()

    # Allow override via command-line argument: --date YYYY-MM-DD
    if len(sys.argv) > 1:
        try:
            target_date = dt.datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD")
            sys.exit(1)

    conn = get_db_connection()

    try:
        # Aggregate the target day
        aggregate_daily_snapshots(conn, target_date)

        # Clean up old aggregates (keep last 2 days)
        delete_old_aggregates(conn, retention_days=2)

        logger.info("Aggregation completed successfully")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
