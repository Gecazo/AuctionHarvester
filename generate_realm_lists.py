import argparse
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from download_realm_auctions import get_access_token, load_credentials, request_json

VALID_REGIONS = ["us", "eu", "kr", "tw"]
MAX_WORKERS = 32  # Parallel requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate realm_lists/<region>_realms.txt")
    parser.add_argument("--region", default=None, help="Single region (compatibility)")
    parser.add_argument("--regions", default="kr,tw", help="Comma-separated regions")
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--end-id", type=int, default=5000)
    parser.add_argument("--stop-after-misses", type=int, default=600)
    return parser.parse_args()


def is_404_error(err: Exception) -> bool:
    return bool(re.search(r"HTTP\s*404", str(err)))


def default_locale(region: str) -> str:
    return {
        "us": "en_US",
        "eu": "en_GB",
        "kr": "ko_KR",
        "tw": "zh_TW",
    }[region]


def discover_region_slugs(region: str, token: str, start_id: int, end_id: int, stop_after_misses: int) -> list[str]:
    namespace = f"dynamic-{region}"
    locale = default_locale(region)
    slugs: set[str] = set()
    
    def fetch_realm(connected_realm_id: int) -> tuple[int, dict | None]:
        """Fetch a single realm and return (id, payload)."""
        try:
            payload = request_json(
                region=region,
                path=f"/data/wow/connected-realm/{connected_realm_id}",
                token=token,
                namespace=namespace,
                locale=locale,
            )
            return connected_realm_id, payload
        except Exception as err:
            if is_404_error(err):
                return connected_realm_id, None
            return connected_realm_id, None
    
    # Parallel requests with early stopping on consecutive misses
    consecutive_misses = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        # Submit initial batch
        for realm_id in range(start_id, min(start_id + MAX_WORKERS * 2, end_id + 1)):
            future = executor.submit(fetch_realm, realm_id)
            futures[future] = realm_id
        
        pbar = tqdm(total=end_id - start_id + 1, desc=f"{region.upper()} connected realms", unit="id", ncols=80, leave=False)
        processed = 0
        
        for future in as_completed(futures):
            realm_id, payload = future.result()
            processed += 1
            pbar.update(1)
            
            if payload is not None:
                consecutive_misses = 0
                for realm in payload.get("realms", []):
                    slug = realm.get("slug") if isinstance(realm, dict) else None
                    if isinstance(slug, str) and slug:
                        slugs.add(slug)
            else:
                consecutive_misses += 1
                # Stop early if too many consecutive misses
                if slugs and consecutive_misses >= stop_after_misses:
                    executor.shutdown(wait=False)
                    pbar.close()
                    return sorted(slugs)
            
            # Submit next batch as futures complete
            next_id = max(futures.values()) + 1 if futures else start_id
            if next_id <= end_id:
                future = executor.submit(fetch_realm, next_id)
                futures[future] = next_id
        
        pbar.close()
    
    return sorted(slugs)


def main() -> None:
    args = parse_args()
    if args.region:
        requested = [args.region.strip().lower()]
    else:
        requested = [part.strip().lower() for part in args.regions.split(",") if part.strip()]
    invalid = [value for value in requested if value not in VALID_REGIONS]
    if invalid:
        raise SystemExit(f"Invalid regions: {', '.join(invalid)}")

    # Check if all requested realm files already exist
    out_dir = pathlib.Path("realm_lists")
    missing_regions = [
        region for region in requested 
        if not (out_dir / f"{region}_realms.txt").exists()
    ]
    
    if not missing_regions:
        print(f"All requested realm lists already exist: {', '.join(requested)}")
        print("Skipping regeneration. Delete files to force regeneration.")
        return

    if missing_regions:
        print(f"Missing realm lists for: {', '.join(missing_regions)}")
        print(f"Will regenerate missing regions only...")

    client_id, client_secret = load_credentials()
    if not client_id or not client_secret:
        raise SystemExit("Set credentials with: python3 setup_credentials.py")

    token = get_access_token(client_id, client_secret)

    out_dir = pathlib.Path("realm_lists")
    out_dir.mkdir(parents=True, exist_ok=True)

    for region in missing_regions:
        slugs = discover_region_slugs(
            region=region,
            token=token,
            start_id=args.start_id,
            end_id=args.end_id,
            stop_after_misses=args.stop_after_misses,
        )
        out_path = out_dir / f"{region}_realms.txt"
        out_path.write_text("\n".join(slugs) + ("\n" if slugs else ""), encoding="utf-8")
        print(f"[{region.upper()}] wrote {len(slugs)} realms -> {out_path}")


if __name__ == "__main__":
    main()
