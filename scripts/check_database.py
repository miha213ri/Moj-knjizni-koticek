"""Read-only connection check for the configured production database."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text
from app.database import engine


def main() -> int:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if engine.dialect.name in {"mysql", "mariadb"}:
                version, database_name = connection.execute(
                    text("SELECT VERSION(), DATABASE()")
                ).one()
            else:
                version, database_name = "SQLite", "local"

        table_names = sorted(inspect(engine).get_table_names())
        print("Povezava z bazo: OK")
        print(f"Tip baze: {engine.dialect.name}")
        print(f"Različica strežnika: {version}")
        print(f"Ime baze: {database_name}")
        print(f"Število tabel: {len(table_names)}")
        for table_name in table_names:
            print(" -", table_name)
        return 0
    except Exception as exc:
        print("POVEZAVA Z BAZO NI USPELA")
        print(f"{type(exc).__name__}: {exc}")
        print("Preveri .env, uporabnika MariaDB in njegove privilegije.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
