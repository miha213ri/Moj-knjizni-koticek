from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Book, BookAuthor, Author, BookISBN
from app.services import clean_isbn, split_values

router = APIRouter()


@router.get("/api/books/suggest")
def book_suggestions(q: str = "", db: Session = Depends(get_db)):
    query = q.strip()
    if len(query) < 2:
        return []
    like = f"%{query}%"
    stmt = select(Book).options(
        selectinload(Book.authors).selectinload(BookAuthor.author),
    ).where(
        or_(
            Book.title.ilike(like),
            Book.subtitle.ilike(like),
            Book.id.in_(select(BookAuthor.book_id).join(Author).where(Author.name.ilike(like))),
        )
    ).order_by(Book.title).limit(15)
    return [
        {
            "id": book.id,
            "title": book.title,
            "authors": ", ".join(link.author.name for link in book.authors),
            "inventory_no": book.inventory_no,
            "label": f"{book.title} — {', '.join(link.author.name for link in book.authors) or 'avtor ni naveden'} [{book.inventory_no}]",
        }
        for book in db.scalars(stmt).unique().all()
    ]


@router.get("/api/isbn-check")
def duplicate_isbn_check(isbns: str = "", db: Session = Depends(get_db)):
    normalized = {clean_isbn(value) for value in split_values(isbns)}
    normalized.discard("")
    if not normalized:
        return {"duplicates": []}
    stmt = select(BookISBN).options(selectinload(BookISBN.book)).where(BookISBN.isbn.in_(normalized))
    found = db.scalars(stmt).all()
    duplicates = []
    seen = set()
    for item in found:
        if item.book_id in seen:
            continue
        seen.add(item.book_id)
        duplicates.append({
            "id": item.book_id,
            "title": item.book.title,
            "inventory_no": item.book.inventory_no,
            "isbn": item.isbn,
        })
    return {"duplicates": duplicates}
