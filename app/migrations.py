"""Small, explicit SQLite migrations for the home-library application."""
from pathlib import Path
import sqlite3

from app.config import DATABASE_URL


def database_path() -> Path:
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("Samodejna migracija je trenutno podprta samo za SQLite.")
    return Path(DATABASE_URL.replace("sqlite:///", "", 1))


def migrate_reading_records() -> None:
    """Allow reading records for books that are not in the home collection."""
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
