"""Read-only MariaDB character-set diagnostic for Moj knjižni kotiček.

The cPanel script runner may start Python with scripts/ as its working
directory. Add the application root to sys.path before importing app.
This script does not modify tables or records.
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import engine


def main() -> None:
    print("=== DATABASE ENCODING DIAGNOSTIC (READ ONLY) ===")
    print("Dialect:", engine.dialect.name)
    if engine.dialect.name != "mysql":
        print("ERROR: Expected MariaDB/MySQL, received:", engine.dialect.name)
        return

    with engine.connect() as conn:
        database_name = conn.exec_driver_sql("SELECT DATABASE()").scalar_one()
        print("Database:", database_name)

        variables = conn.exec_driver_sql(
            "SHOW VARIABLES WHERE Variable_name IN "
            "('character_set_client','character_set_connection',"
            "'character_set_results','character_set_database',"
            "'character_set_server','collation_connection','collation_database')"
        ).all()
        print("-- Connection/server variables --")
        for name, value in variables:
            print(f"{name}={value}")

        probe = conn.exec_driver_sql(
            "SELECT %s", ("č Š ž Č Š Ž",)
        ).scalar_one()
        expected = "č Š ž Č Š Ž".encode("utf-8")
        actual = str(probe).encode("utf-8")
        print("-- UTF-8 round trip --")
        print("expected_utf8_hex:", expected.hex())
        print("actual_utf8_hex:  ", actual.hex())
        print("round_trip_ok:", actual == expected)

        tables = conn.exec_driver_sql(
            "SELECT TABLE_NAME, TABLE_COLLATION "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME"
        ).all()
        print("-- Table collations --")
        for table_name, collation in tables:
            print(f"{table_name}: {collation}")

        bad_columns = conn.exec_driver_sql(
            "SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND CHARACTER_SET_NAME IS NOT NULL "
            "AND CHARACTER_SET_NAME NOT IN ('utf8mb4','utf8mb3') "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        ).all()
        print("-- Text columns not using UTF-8 --")
        if not bad_columns:
            print("NONE")
        else:
            for row in bad_columns:
                print(" | ".join(str(value) for value in row))

        print("-- Tables that may need conversion to utf8mb4 --")
        affected_names = {
            str(name) for name, collation in tables
            if not (collation or "").lower().startswith("utf8mb4")
        }
        affected_names.update(str(row[0]) for row in bad_columns)
        if not affected_names:
            print("NONE")
        else:
            table_collations = {str(name): collation for name, collation in tables}
            for name in sorted(affected_names):
                safe_name = name.replace("`", "``")
                print(f"-- Current table collation: {table_collations.get(name)}")
                print(
                    f"ALTER TABLE `{safe_name}` CONVERT TO CHARACTER SET "
                    "utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )

    print("=== END; NO DATA OR SCHEMA WAS CHANGED ===")


if __name__ == "__main__":
    main()
