import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, date, timedelta
from tqdm import tqdm


VALID_REGIONS = {"us", "eu", "kr", "tw"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run periodic auction updates and DB ingest"
    )
    parser.add_argument(
        "--region",
        default=None,
        choices=sorted(VALID_REGIONS),
        help="Single region to update (kept for compatibility)",
    )
    parser.add_argument(
        "--regions",
        default="eu",
        help="Comma-separated regions to update, e.g. eu,us",
    )
    parser.add_argument("--interval-minutes", type=int, default=20)
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    return parser.parse_args()


def parse_regions(region: str | None, regions: str) -> list[str]:
    if region:
        return [region]

    parsed = [part.strip().lower() for part in regions.split(",") if part.strip()]
    invalid = [value for value in parsed if value not in VALID_REGIONS]
    if invalid:
        raise SystemExit(f"Invalid regions: {', '.join(invalid)}")
    if not parsed:
        raise SystemExit("No regions provided")
    return parsed


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def get_time_to_midnight() -> float:
    """Calculate seconds until midnight UTC."""
    now = datetime.now(timezone.utc)
    tomorrow_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    seconds_to_midnight = (tomorrow_midnight - now).total_seconds()
    return seconds_to_midnight


def show_progress_bars(sleep_seconds: int) -> None:
    """Display progress bars for next update and next daily aggregation."""
    seconds_to_midnight = get_time_to_midnight()
    
    # Progress bar for next update
    print("\n" + "=" * 60)
    for _ in tqdm(range(sleep_seconds), desc="Next update", unit="s", unit_scale=True):
        time.sleep(1)
    
    # Show time until next aggregation
    seconds_to_midnight = get_time_to_midnight()
    hours = int(seconds_to_midnight // 3600)
    minutes = int((seconds_to_midnight % 3600) // 60)
    print(f"Next daily aggregation: {hours}h {minutes}m")
    print("=" * 60 + "\n")


def run_cycle(region: str, output_dir: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting update cycle for {region.upper()}")

    run_command(
        [
            sys.executable,
            "download_realm_auctions.py",
            "--region",
            region,
            "--all",
            "--output-dir",
            output_dir,
        ]
    )

    run_command(
        [
            sys.executable,
            "ingest_auctions_to_postgres.py",
            "--glob",
            f"{output_dir}/auctions_*_{region}.json",
        ]
    )

    print(f"[{datetime.now(timezone.utc).isoformat()}] Cycle completed for {region.upper()}")


def run_daily_aggregation() -> None:
    """Run the daily aggregation script for the previous day."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Running daily aggregation...")
    try:
        run_command([sys.executable, "aggregate_daily_snapshots.py"])
        print(f"[{datetime.now(timezone.utc).isoformat()}] Daily aggregation completed")
    except subprocess.CalledProcessError as err:
        print(
            f"Daily aggregation failed with exit code {err.returncode}",
            file=sys.stderr,
        )


def main() -> None:
    args = parse_args()
    regions = parse_regions(args.region, args.regions)
    
    # Track the last aggregation date to run it once per day at midnight
    last_aggregation_date = date.today()

    while True:
        # Check if we've crossed into a new day
        current_date = date.today()
        if current_date > last_aggregation_date:
            run_daily_aggregation()
            last_aggregation_date = current_date
        
        for region in regions:
            try:
                run_cycle(region=region, output_dir=args.output_dir)
            except subprocess.CalledProcessError as err:
                print(
                    f"Cycle failed for {region.upper()} with exit code {err.returncode}",
                    file=sys.stderr,
                )

        if args.once:
            break

        sleep_seconds = max(args.interval_minutes, 1) * 60
        show_progress_bars(sleep_seconds)


if __name__ == "__main__":
    main()
