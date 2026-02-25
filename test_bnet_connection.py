import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> None:
    client_id = os.getenv("BLIZZARD_CLIENT_ID")
    client_secret = os.getenv("BLIZZARD_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Set BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET", file=sys.stderr)
        raise SystemExit(1)

    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()

    req = urllib.request.Request(
        "https://oauth.battle.net/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = response.read()
        if b"access_token" not in payload:
            print("Connection failed: no access_token in response", file=sys.stderr)
            raise SystemExit(1)
        print("Connected to Battle.net API")
    except urllib.error.URLError as err:
        print(f"Connection failed: {err}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
