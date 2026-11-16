"""Samodejne in varne migracije podatkovne sheme za SQLite in MariaDB."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)


def auto_migrate_schema(engine: Engine) -> None:
    """Preveri obstoječe tabele in po potrebi doda manjkajoče stolpce ter indekse."""
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        if "users" in tables:
            user_columns = {col["name"] for col in inspector.get_columns("users")}
            new_columns = [
                ("role", "VARCHAR(20) NOT NULL DEFAULT 'USER'"),
                ("email", "VARCHAR(180) NULL"),
                ("session_version", "INTEGER NOT NULL DEFAULT 1"),
                ("failed_logins", "INTEGER NOT NULL DEFAULT 0"),
                ("locked_until", "DATETIME NULL"),
                ("last_login_at", "DATETIME NULL"),
                ("updated_at", "DATETIME NULL"),
            ]
            with engine.begin() as conn:
                for col_name, col_def in new_columns:
                    if col_name not in user_columns:
                        logger.info("Dodajam manjkajoči stolpec users.%s...", col_name)
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))

        if engine.dialect.name == "sqlite":
            migrate_reading_records()

    except Exception as exc:
        logger.warning("Opozorilo pri samodejni migraciji sheme: %s", exc)


def database_path() -> Path:
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("Samodejna migracija je trenutno podprta samo za SQLite.")
    return Path(DATABASE_URL.replace("sqlite:///", "", 1))


def migrate_reading_records() -> None:
    """Omogoča beleženje bralnega dnevnika tudi za knjige izven domače knjižnice."""
    try:
        path = database_path()
        if not path.exists():
            return
        connection = sqlite3.connect(path)
        try:
            columns = connection.execute("PRAGMA table_info(reading_records)").fetchall()
            if not columns:
                return
            names = {column[1] for column in columns}
            book_column = next((column for column in columns if column[1] == "book_id"), None)
            needs_rebuild = "external_title" not in names or (book_column and book_column[3] == 1)
            if not needs_rebuild:
                return

            connection.commit()
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ALTER TABLE reading_records RENAME TO reading_records_old")
            connection.execute("""
                CREATE TABLE reading_records (
                    id INTEGER NOT NULL PRIMARY KEY,
                    book_id INTEGER NULL,
                    external_title VARCHAR(300) NULL,
                    member_id INTEGER NOT NULL,
                    start_date DATE NULL,
                    finish_date DATE NULL,
                    rating INTEGER NULL,
                    comment TEXT NULL,
                    completed BOOLEAN NOT NULL DEFAULT 1,
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                    FOREIGN KEY(member_id) REFERENCES family_members(id)
                )
            """)
            old_names = {column[1] for column in connection.execute("PRAGMA table_info(reading_records_old)")}
            wanted = ["id", "book_id", "member_id", "start_date", "finish_date", "rating", "comment", "completed"]
            if not set(wanted).issubset(old_names):
                raise RuntimeError("Stara tabela bralnega dnevnika nima pričakovane strukture.")
            connection.execute("""
                INSERT INTO reading_records
                    (id, book_id, external_title, member_id, start_date, finish_date, rating, comment, completed)
                SELECT id, book_id, NULL, member_id, start_date, finish_date, rating, comment, completed
                FROM reading_records_old
            """)
            connection.execute("DROP TABLE reading_records_old")
            connection.execute("CREATE INDEX IF NOT EXISTS ix_reading_records_book_id ON reading_records(book_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS ix_reading_records_member_id ON reading_records(member_id)")
            connection.commit()
            connection.execute("PRAGMA foreign_keys=ON")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except Exception as exc:
        logger.warning("Opozorilo pri migraciji bralnega dnevnika: %s", exc)
