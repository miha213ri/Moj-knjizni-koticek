"""Shared catalog helpers. Persistent cover images are stored in the database."""
from __future__ import annotations

from datetime import date
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Book, Author, BookAuthor, BookISBN, Room, Cabinet, Shelf, Loan


def new_inventory_no(db: Session) -> str:
    existing = set(db.scalars(select(Book.inventory_no)).all())
    number = 1
    while True:
        candidate = f"K-{number:06d}"
        if candidate not in existing:
            return candidate
        number += 1


def clean_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def is_isbn(value: str) -> bool:
    cleaned = clean_isbn(value)
    return len(cleaned) in (10, 13) and cleaned[:-1].isdigit() and (cleaned[-1].isdigit() or cleaned[-1] == "X")


def split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\n]+", value or "") if item.strip()]


def get_book(db: Session, book_id: int):
    return db.scalar(
        select(Book).where(Book.id == book_id).options(
            selectinload(Book.location),
            selectinload(Book.authors).selectinload(BookAuthor.author),
            selectinload(Book.isbns), selectinload(Book.genre),
            selectinload(Book.collection), selectinload(Book.room),
            selectinload(Book.cabinet), selectinload(Book.shelf),
            selectinload(Book.loans).selectinload(Loan.borrower),
        )
    )


def active_loan(book: Book):
    active = [loan for loan in book.loans if loan.returned_date is None]
    return max(active, key=lambda item: item.id) if active else None


def find_named(db: Session, model, name: str, *, parent_field=None, parent_id=None, exclude_id=None):
    """Unicode-aware lookup for small dictionary tables (SQLite lower is ASCII-only)."""
    stmt = select(model)
    if parent_field is not None:
        stmt = stmt.where(parent_field == parent_id)
    for item in db.scalars(stmt).all():
        if item.id != exclude_id and item.name.casefold() == (name or "").strip().casefold():
            return item
    return None


def ensure_named(db: Session, model, name: str):
    name = (name or "").strip()
    if not name:
        return None
    obj = find_named(db, model, name)
    if obj is None:
        obj = model(name=name)
        db.add(obj)
        db.flush()
    return obj


def ensure_location(db: Session, room_name: str, cabinet_name: str, shelf_name: str, location_id: int):
    """Create a room/cabinet/shelf hierarchy within one physical library."""
    room = find_named(db, Room, room_name, parent_field=Room.location_id, parent_id=location_id) if room_name.strip() else None
    if room is None and room_name.strip():
        room = Room(location_id=location_id, name=room_name.strip())
        db.add(room)
        db.flush()
    cabinet = None
    shelf = None
    if room and cabinet_name.strip():
        cabinet = find_named(db, Cabinet, cabinet_name, parent_field=Cabinet.room_id, parent_id=room.id)
        if cabinet is None:
            cabinet = Cabinet(room_id=room.id, name=cabinet_name.strip())
            db.add(cabinet)
            db.flush()
    if cabinet and shelf_name.strip():
        shelf = find_named(db, Shelf, shelf_name, parent_field=Shelf.cabinet_id, parent_id=cabinet.id)
        if shelf is None:
            shelf = Shelf(cabinet_id=cabinet.id, name=shelf_name.strip())
            db.add(shelf)
            db.flush()
    return room, cabinet, shelf


def set_authors(db: Session, book: Book, names: str):
    book.authors.clear()
    for position, name in enumerate(split_values(names)):
        author = ensure_named(db, Author, name)
        if author:
            book.authors.append(BookAuthor(author=author, position=position))


def set_isbns(db: Session, book: Book, values: str):
    book.isbns.clear()
    seen = set()
    for value in split_values(values):
        cleaned = clean_isbn(value)
        if cleaned and cleaned not in seen:
            book.isbns.append(BookISBN(isbn=cleaned))
            seen.add(cleaned)


# Public re-exports retained for the existing route modules.
from app.catalog import lookup_book, save_cover, save_uploaded_cover  # noqa: E402
