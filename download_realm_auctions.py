import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


VALID_REGIONS = {"us", "eu", "kr", "tw"}


def load_credentials() -> tuple[str | None, str | None]:
    client_id = os.getenv("BLIZZARD_CLIENT_ID")
    client_secret = os.getenv("BLIZZARD_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret

    if not os.path.exists(".env"):
        return None, None

    values: dict[str, str] = {}
    with open(".env", "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values.get("BLIZZARD_CLIENT_ID"), values.get("BLIZZARD_CLIENT_SECRET")


def get_access_token(client_id: str, client_secret: str) -> str:
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth.battle.net/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    token = payload.get("access_token")
    if not token:
        raise RuntimeError("No access_token in OAuth response")
    return token


def request_json(region: str, path: str, token: str, namespace: str, locale: str) -> dict:
    base = f"https://{region}.api.blizzard.com{path}"

    query_style = (
        base
        + "?"
        + urllib.parse.urlencode(
            {
                "namespace": namespace,
                "locale": locale,
                "access_token": token,
            }
        )
    )

    try:
        with urllib.request.urlopen(query_style, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as first_error:
        header_style_url = base + "?" + urllib.parse.urlencode({"locale": locale})
        req = urllib.request.Request(
            header_style_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Battlenet-Namespace": namespace,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as second_error:
            first_body = first_error.read().decode("utf-8", errors="replace")
            second_body = second_error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Failed {path}. Query-style HTTP {first_error.code}: {first_body[:200]} | "
                f"Header-style HTTP {second_error.code}: {second_body[:200]}"
            ) from second_error


def parse_connected_realm_id(payload: dict) -> int:
    href = payload.get("connected_realm", {}).get("href", "")
    match = re.search(r"/connected-realm/(\d+)", href)
    if not match:
        raise RuntimeError("Could not parse connected realm id from realm response")
    return int(match.group(1))


def realm_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def default_locale_for_region(region: str) -> str:
    return {
        "us": "en_US",
        "eu": "en_GB",
        "kr": "ko_KR",
        "tw": "zh_TW",
    }[region]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download auctions for one WoW realm")
    parser.add_argument("--region", default="eu", choices=sorted(VALID_REGIONS))
    parser.add_argument("--realm", default="kazzak", help="Realm name (example: kazzak)")
    parser.add_argument("--locale", default=None, help="Optional locale override (example: en_GB)")
    parser.add_argument("--output", default=None, help="Optional output file path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    region = args.region
    realm = realm_slug(args.realm)
    locale = args.locale or default_locale_for_region(region)

    client_id, client_secret = load_credentials()
    if not client_id or not client_secret:
        print("Set credentials with: python3 setup_credentials.py", file=sys.stderr)
        raise SystemExit(1)

    try:
        token = get_access_token(client_id, client_secret)
        namespace = f"dynamic-{region}"

        realm_payload = request_json(
            region=region,
            path=f"/data/wow/realm/{realm}",
            token=token,
            namespace=namespace,
            locale=locale,
        )
        connected_realm_id = parse_connected_realm_id(realm_payload)

        auctions_payload = request_json(
            region=region,
            path=f"/data/wow/connected-realm/{connected_realm_id}/auctions",
            token=token,
            namespace=namespace,
            locale=locale,
        )

        out_path = (
            pathlib.Path(args.output)
            if args.output
            else pathlib.Path("data") / f"auctions_{realm}_{region}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as file:
            json.dump(auctions_payload, file, indent=2)

        auctions_count = len(auctions_payload.get("auctions", []))
        print(f"Saved {auctions_count} auctions to {out_path}")
        print(f"Realm: {realm} ({region.upper()})")
        print(f"Connected realm ID: {connected_realm_id}")
    except RuntimeError as err:
        print(f"Request failed: {err}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as err:
        print(f"Network error: {err}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
