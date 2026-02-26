import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone


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


def main() -> None:
    args = parse_args()
    regions = parse_regions(args.region, args.regions)

    while True:
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
        print(f"Sleeping {sleep_seconds} seconds...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
