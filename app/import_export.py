"""Excel template and robust XLSX import for the family library."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import logging
import traceback
import uuid

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Collection, Genre
from app.services import ensure_location, ensure_named, set_authors, set_isbns


HEADERS = [
    "Inventarna številka", "Naslov", "Podnaslov", "Avtorji", "Leto",
    "Založba", "Kraj izdaje", "Jezik", "Žanr", "Zbirka",
    "ISBN številke", "Soba", "Omara", "Polica", "Povzetek",
    "Posebna opomba", "Posebna izdaja", "Stanje knjige",
    "Datum pridobitve", "Cena", "Vir pridobitve",
]

logger = logging.getLogger(__name__)

# Common language codes used in catalogues. Their presence in the "Žanr"
# column, together with a city in "Jezik", is a strong signal of a shifted row.
_LANGUAGE_CODES = {
    "sl", "en", "de", "it", "fr", "hr", "sr", "bs", "es", "pt", "nl",
    "ru", "uk", "pl", "cs", "sk", "hu", "ro", "bg", "el", "tr", "ar",
    "he", "ja", "zh", "ko", "la", "sv", "no", "da", "fi", "et", "lv",
    "lt", "is",
}


def _write_import_log(message: str, exc: BaseException | None = None) -> None:
    """Write import diagnostics to a dedicated file in the application's tmp folder."""
    log_path = Path(__file__).resolve().parent.parent / "tmp" / "import_xlsx.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{stamp}] {message}\n")
            if exc is not None:
                handle.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            handle.flush()
    except Exception:
        # Logging must never be the reason an otherwise valid import fails.
        logger.exception("Ne morem zapisati dnevnika uvoza XLSX v %s", log_path)


def log_import_error(message: str, exc: BaseException | None = None) -> None:
    """Public helper used by the route for request-level failures and diagnostics."""
    _write_import_log(message, exc)


def template_bytes():
    wb = Workbook()
    ws = wb.active
    ws.title = "Knjige"
    ws.append(HEADERS)
    ws.append([
        "K-000001", "Primer knjige", "", "Avtor Primer", 2020, "Založba", "", "sl",
        "Roman", "", "9780000000000", "Dnevna soba", "Omara 1", "Polica 1", "", "",
        "Ne", "Zelo dobro", "", "", "Darilo",
    ])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def _parse_year(value, row_num: int) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Vrstica {row_num}: v stolpcu 'Leto' je neveljavna vrednost {value!r}.")
    try:
        if isinstance(value, int):
            year = value
        elif isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            year = int(value)
        else:
            text = str(value).strip()
            if not text.isdigit():
                raise ValueError
            year = int(text)
        if year < 0 or year > 9999:
            raise ValueError
        return year
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            f"Vrstica {row_num}: v stolpcu 'Leto' je vrednost {value!r}; "
            "pričakovana je letnica (npr. 1998). Vrstica ni bila uvožena."
        ) from None


def _looks_like_year(value) -> bool:
    try:
        year = _parse_year(value, 0)
    except ValueError:
        return False
    # Used only to detect a displaced year cell, not to validate ordinary years.
    return year is not None and 1000 <= year <= 2100


def _join_subtitle_parts(first, extra) -> str | None:
    first_text = str(first or "").strip()
    extra_text = str(extra or "").strip()
    if first_text and extra_text:
        return f"{first_text}: {extra_text}"
    return first_text or extra_text or None


def _repair_known_shifted_row(row: dict, row_num: int) -> tuple[dict, bool]:
    """Repair a row with an extra title fragment before author and one omitted note.

    In the supplied workbook rows 44 and 48 have this exact structure:
    - column D contains a continuation of the subtitle;
    - column E contains the author and F contains the publication year;
    - subsequent bibliographic columns through summary are shifted one place;
    - "Posebna opomba" is absent; special-edition/condition/date/price fields
      are already back in their normal columns.

    All original text is preserved: the extra title fragment is appended to
    the subtitle, and the missing special note remains empty.
    """
    raw_year = row.get("Leto")
    raw_year_in_publisher = row.get("Založba")
    language_candidate = str(row.get("Žanr") or "").strip().casefold()
    current_language = str(row.get("Jezik") or "").strip().casefold()

    shifted_pattern = (
        raw_year not in (None, "")
        and not _looks_like_year(raw_year)
        and _looks_like_year(raw_year_in_publisher)
        and language_candidate in _LANGUAGE_CODES
        and current_language not in _LANGUAGE_CODES
        and bool(str(row.get("Kraj izdaje") or "").strip())
    )
    if not shifted_pattern:
        return row, False

    fixed = dict(row)
    fixed["Podnaslov"] = _join_subtitle_parts(row.get("Podnaslov"), row.get("Avtorji"))
    fixed["Avtorji"] = row.get("Leto")
    fixed["Leto"] = row.get("Založba")
    fixed["Založba"] = row.get("Kraj izdaje")
    fixed["Kraj izdaje"] = row.get("Jezik")
    fixed["Jezik"] = row.get("Žanr")
    fixed["Žanr"] = row.get("Zbirka")
    fixed["Zbirka"] = row.get("ISBN številke")
    fixed["ISBN številke"] = row.get("Soba")
    fixed["Soba"] = row.get("Omara")
    fixed["Omara"] = row.get("Polica")
    fixed["Polica"] = row.get("Povzetek")
    fixed["Povzetek"] = row.get("Posebna opomba")
    fixed["Posebna opomba"] = None

    _write_import_log(
        f"Vrstica {row_num}: samodejno poravnana struktura; "
        "dodatno besedilo je združeno v Podnaslov, manjkajoča Posebna opomba ostane prazna."
    )
    return fixed, True


def _parse_acquisition_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def import_xlsx(db: Session, content: bytes, location_id: int):
    """Import rows independently; a malformed row cannot poison the DB transaction."""
    _write_import_log(
        f"Začetek uvoza XLSX: location_id={location_id}, velikost={len(content)} B"
    )
    wb = None
    try:
        try:
            wb = load_workbook(BytesIO(content), data_only=True, read_only=True)
            ws = wb.active
            if ws.max_row < 1 or ws.max_column < 1:
                raise ValueError("Excelova datoteka ne vsebuje podatkov.")
            headers = [str(cell.value or "").strip() for cell in ws[1]]
            if "Naslov" not in headers:
                raise ValueError("V Excelovi datoteki manjka obvezni stolpec 'Naslov'. Uporabi predlogo aplikacije.")
            if len(headers) != len(set(headers)):
                raise ValueError("Excelova datoteka vsebuje podvojene naslove stolpcev.")
        except Exception as exc:
            _write_import_log("Datoteke XLSX ni bilo mogoče odpreti ali preveriti glave.", exc)
            raise ValueError(
                "Datoteke ni mogoče prebrati kot veljavne Excelove datoteke ali pa nima pravilne glave. "
                "Prenesi novo predlogo in poskusi znova."
            ) from exc

        imported = 0
        repaired_count = 0
        errors: list[str] = []
        for row_num, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            row = {header: value for header, value in zip(headers, values) if header}
            title = str(row.get("Naslov") or "").strip()
            if not title:
                continue

            row, repaired = _repair_known_shifted_row(row, row_num)
            if repaired:
                repaired_count += 1
            try:
                year = _parse_year(row.get("Leto"), row_num)
            except ValueError as exc:
                errors.append(str(exc))
                _write_import_log(str(exc))
                continue

            inventory = str(row.get("Inventarna številka") or "").strip() or None
            duplicate_message = None
            try:
                # The savepoint rolls back this row only if a database constraint fails.
                with db.begin_nested():
                    if inventory and db.scalar(
                        select(Book.id).where(Book.inventory_no == inventory).limit(1)
                    ):
                        duplicate_message = (
                            f"Vrstica {row_num}: inventarna številka {inventory} že obstaja."
                        )
                    else:
                        room, cabinet, shelf = ensure_location(
                            db,
                            str(row.get("Soba") or ""),
                            str(row.get("Omara") or ""),
                            str(row.get("Polica") or ""),
                            location_id,
                        )
                        genre = ensure_named(db, Genre, str(row.get("Žanr") or ""))
                        collection = ensure_named(db, Collection, str(row.get("Zbirka") or ""))
                        book = Book(
                            location_id=location_id,
                            inventory_no=inventory or f"K-{uuid.uuid4().hex[:8].upper()}",
                            title=title,
                            subtitle=str(row.get("Podnaslov") or "") or None,
                            year=year,
                            publisher=str(row.get("Založba") or "") or None,
                            publication_place=str(row.get("Kraj izdaje") or "") or None,
                            language=str(row.get("Jezik") or "") or None,
                            genre=genre,
                            collection=collection,
                            special_edition=str(row.get("Posebna izdaja") or "").strip().casefold()
                            in ("da", "yes", "1", "true"),
                            summary=str(row.get("Povzetek") or "") or None,
                            special_note=str(row.get("Posebna opomba") or "") or None,
                            condition=str(row.get("Stanje knjige") or "") or None,
                            acquisition_source=str(row.get("Vir pridobitve") or "") or None,
                            purchase_price=str(row.get("Cena") or "") or None,
                            acquisition_date=_parse_acquisition_date(row.get("Datum pridobitve")),
                            room=room,
                            cabinet=cabinet,
                            shelf=shelf,
                        )
                        db.add(book)
                        db.flush()
                        set_authors(db, book, str(row.get("Avtorji") or ""))
                        set_isbns(db, book, str(row.get("ISBN številke") or ""))
                        db.flush()

                if duplicate_message:
                    errors.append(duplicate_message)
                    _write_import_log(duplicate_message)
                else:
                    imported += 1
            except Exception as exc:
                message = f"Vrstica {row_num} ({title[:100]}): {type(exc).__name__}: {exc}"
                errors.append(message)
                _write_import_log(message, exc)

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            _write_import_log("Končni commit uvoza XLSX ni uspel; izveden je rollback.", exc)
            raise

        _write_import_log(
            f"Zaključen uvoz XLSX: uspešno={imported}, napake={len(errors)}, "
            f"samodejno_poravnanih={repaired_count}, location_id={location_id}"
        )
        return imported, errors
    finally:
        if wb is not None:
            wb.close()
