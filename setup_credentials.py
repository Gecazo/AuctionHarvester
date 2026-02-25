from pathlib import Path


def main() -> None:
    client_id = input("BLIZZARD_CLIENT_ID: ").strip()
    client_secret = input("BLIZZARD_CLIENT_SECRET: ").strip()

    if not client_id or not client_secret:
        print("Both values are required.")
        raise SystemExit(1)

    env_content = (
        f'BLIZZARD_CLIENT_ID="{client_id}"\n'
        f'BLIZZARD_CLIENT_SECRET="{client_secret}"\n'
    )

    Path(".env").write_text(env_content, encoding="utf-8")
    print("Saved credentials to .env")


if __name__ == "__main__":
    main()
