import os
import pathlib
import sys

import psycopg


def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://auction:auction@localhost:5432/auctionharvester",
    )

    schema_path = pathlib.Path("postgres_schema.sql")
    if not schema_path.exists():
        print("Missing postgres_schema.sql", file=sys.stderr)
        raise SystemExit(1)

    sql = schema_path.read_text(encoding="utf-8")

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

    print("PostgreSQL schema initialized.")


if __name__ == "__main__":
    main()
