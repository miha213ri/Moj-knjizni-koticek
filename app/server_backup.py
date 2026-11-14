"""Database-native backup for the MariaDB deployment (cover BLOBs included)."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, TextIOWrapper
import base64
import gzip
import json
import zipfile

from sqlalchemy import inspect
from app.database import engine, Base


def _encode(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__type__": "bytes", "value": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    return value


def _decode(value):
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind, raw = value["__type__"], value.get("value")
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "bytes":
        return base64.b64decode(raw, validate=True)
    if kind == "decimal":
        return Decimal(raw)
    raise ValueError("Varnostna kopija vsebuje neznan podatkovni tip.")


def _snapshot():
    tables = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            result = connection.execute(table.select()).mappings().all()
            tables[table.name] = [
                {key: _encode(value) for key, value in row.items()}
                for row in result
            ]
    return {
        "format": "moj-knjizni-koticek-db-v1",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "tables": tables,
    }


def create_full_backup() -> bytes:
    payload = json.dumps(_snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps({"format": "moj-knjizni-koticek-db-v1", "contains": "database + cover images"}, ensure_ascii=False))
        archive.writestr("database.json", payload)
    return stream.getvalue()


def create_database_export() -> bytes:
    payload = json.dumps(_snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(payload, compresslevel=6)


def restore_full_backup(content: bytes, filename: str) -> None:
    if not content or len(content) > 300 * 1024 * 1024:
        raise ValueError("Datoteka je prazna ali presega 300 MB.")
    try:
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if "database.json" not in archive.namelist():
                    raise ValueError("ZIP ne vsebuje database.json.")
                info = archive.getinfo("database.json")
                if info.file_size > 350 * 1024 * 1024:
                    raise ValueError("Podatkovni del ZIP-kopije presega 350 MB.")
                raw = archive.read("database.json")
        elif filename.lower().endswith((".json.gz", ".gz")):
            with gzip.GzipFile(fileobj=BytesIO(content), mode="rb") as compressed:
                raw = compressed.read(350 * 1024 * 1024 + 1)
                if len(raw) > 350 * 1024 * 1024:
                    raise ValueError("Razširjena varnostna kopija presega 350 MB.")
        else:
            raise ValueError("Izberi varnostno kopijo .zip ali .json.gz.")
        document = json.loads(raw.decode("utf-8"))
    except (zipfile.BadZipFile, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Varnostna kopija ni veljavna.") from exc

    if document.get("format") != "moj-knjizni-koticek-db-v1" or not isinstance(document.get("tables"), dict):
        raise ValueError("Neznana oblika varnostne kopije.")

    metadata_tables = {table.name: table for table in Base.metadata.sorted_tables}
    supplied_tables = document["tables"]
    unknown = set(supplied_tables) - set(metadata_tables)
    missing = set(metadata_tables) - set(supplied_tables)
    if unknown:
        raise ValueError("Varnostna kopija vsebuje neznane tabele: " + ", ".join(sorted(unknown)))
    if missing:
        raise ValueError("Varnostna kopija ne vsebuje vseh tabel te različice: " + ", ".join(sorted(missing)))
    for table_name, rows in supplied_tables.items():
        if not isinstance(rows, list):
            raise ValueError(f"Neveljavni podatki v tabeli {table_name}.")
        valid_columns = {column.name for column in metadata_tables[table_name].columns}
        if any(not isinstance(row, dict) or set(row) - valid_columns for row in rows):
            raise ValueError(f"Neveljavni stolpci v tabeli {table_name}.")

    tables = Base.metadata.sorted_tables
    with engine.connect() as connection:
        is_mysql = engine.dialect.name in ("mysql", "mariadb")
        is_sqlite = engine.dialect.name == "sqlite"
        if is_mysql:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            connection.commit()
        elif is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        transaction = connection.begin()
        try:
            for table in reversed(tables):
                connection.execute(table.delete())
            for table in tables:
                rows = supplied_tables.get(table.name, [])
                if rows:
                    decoded = [{key: _decode(value) for key, value in row.items()} for row in rows]
                    connection.execute(table.insert(), decoded)
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            if is_mysql:
                connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
                connection.commit()
            elif is_sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


def database_health() -> dict:
    inspector = inspect(engine)
    return {"dialect": engine.dialect.name, "tables": inspector.get_table_names()}
