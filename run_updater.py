import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from threading import Thread



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
    for i in range(sleep_seconds):
        remaining_seconds = sleep_seconds - i - 1
        minutes = remaining_seconds // 60
        secs = remaining_seconds % 60
        print(f"Next update in: {minutes:02d}m {secs:02d}s", end="\r")
        time.sleep(1)
    print("                    ")
    
    # Show time until next aggregation
    seconds_to_midnight = get_time_to_midnight()
    hours = int(seconds_to_midnight // 3600)
    minutes = int((seconds_to_midnight % 3600) // 60)
    print(f"Next daily aggregation: {hours}h {minutes}m")
    print("=" * 60 + "\n")


def run_cycle(region: str, output_dir: str, position: int | None = None) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting update cycle for {region.upper()}")

    cmd = [
        sys.executable,
        "download_realm_auctions.py",
        "--region",
        region,
        "--all",
        "--output-dir",
        output_dir,
    ]
    if position is not None:
        cmd.extend(["--position", str(position)])
    
    run_command(cmd)

    ingest_cmd = [
        sys.executable,
        "ingest_auctions_to_postgres.py",
        "--glob",
        f"{output_dir}/auctions_*_{region}.json",
    ]
    if position is not None:
        ingest_cmd.extend(["--position", str(position)])
    
    run_command(ingest_cmd)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Cycle completed for {region.upper()}")


def run_daily_aggregation() -> None:
    """Run the windowed aggregation and clean up old snapshots."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Running windowed aggregation (morning/day/evening/night)...")
    try:
        run_command([sys.executable, "aggregate_windowed_snapshots.py"])
        print(f"[{datetime.now(timezone.utc).isoformat()}] Windowed aggregation completed")
    except subprocess.CalledProcessError as err:
        print(
            f"Windowed aggregation failed with exit code {err.returncode}",
            file=sys.stderr,
        )


def run_region_cycle(region: str, output_dir: str, position: int | None = None) -> None:
    """Run cycle for a single region with error handling."""
    try:
        run_cycle(region=region, output_dir=output_dir, position=position)
    except subprocess.CalledProcessError as err:
        print(
            f"Cycle failed for {region.upper()} with exit code {err.returncode}",
            file=sys.stderr,
        )


def main() -> None:
    args = parse_args()
    regions = parse_regions(args.region, args.regions)
    
    # Track the last aggregation date to run it once per day at midnight (UTC)
    last_aggregation_date = datetime.now(timezone.utc).date()

    while True:
        # Check if we've crossed into a new day (UTC)
        current_date = datetime.now(timezone.utc).date()
        if current_date > last_aggregation_date:
            run_daily_aggregation()
            last_aggregation_date = current_date
        
        # Run all regions in parallel threads
        threads = []
        for idx, region in enumerate(regions):
            thread = Thread(target=run_region_cycle, args=(region, args.output_dir, idx))
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        if args.once:
            break

        sleep_seconds = max(args.interval_minutes, 1) * 60
        show_progress_bars(sleep_seconds)


if __name__ == "__main__":
    main()
