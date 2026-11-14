from datetime import date, timedelta
from io import BytesIO
import logging
from urllib.parse import quote_plus, urlencode
import re

from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import select, or_, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from app.database import get_db
from app.models import (
    Book, BookAuthor, BookISBN, Author, Genre, Collection, Room, Cabinet,
    Shelf, Borrower, Loan, CoverImage, Location, ReadingRecord,
)
from app.services import (
    get_book, active_loan, ensure_named, set_authors, set_isbns, clean_isbn,
    lookup_book, save_cover, save_uploaded_cover, new_inventory_no,
)
from app.route_helpers import render, date_value, redirect_notice, book_form_context
from app.access import current_location_id, require_location, is_admin, allowed_location_ids

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/books")


def _book_listing_rows(db: Session, q: str = ""):
    """Return the one canonical filtered book list used by both HTML and XLSX."""
    stmt = select(Book).options(
        selectinload(Book.authors).selectinload(BookAuthor.author),
        selectinload(Book.isbns), selectinload(Book.room), selectinload(Book.cabinet),
        selectinload(Book.shelf), selectinload(Book.location),
        selectinload(Book.genre), selectinload(Book.collection),
        selectinload(Book.loans).selectinload(Loan.borrower),
    )

    if q.strip():
        needle = q.strip()
        like = f"%{needle}%"
        conditions = [
            Book.title.ilike(like), Book.subtitle.ilike(like),
            Book.inventory_no.ilike(like), Book.publication_place.ilike(like),
            Book.publisher.ilike(like), Book.language.ilike(like),
            Book.summary.ilike(like), Book.special_note.ilike(like),
            Book.id.in_(select(BookAuthor.book_id).join(Author).where(Author.name.ilike(like))),
            Book.id.in_(select(BookISBN.book_id).where(BookISBN.isbn.ilike(like))),
            Book.genre_id.in_(select(Genre.id).where(Genre.name.ilike(like))),
            Book.collection_id.in_(select(Collection.id).where(Collection.name.ilike(like))),
            Book.location_id.in_(select(Location.id).where(Location.name.ilike(like))),
            Book.room_id.in_(select(Room.id).where(Room.name.ilike(like))),
            Book.cabinet_id.in_(select(Cabinet.id).where(Cabinet.name.ilike(like))),
            Book.shelf_id.in_(select(Shelf.id).where(Shelf.name.ilike(like))),
        ]
        normalized = clean_isbn(needle)
        if normalized:
            conditions.append(
                Book.id.in_(select(BookISBN.book_id).where(BookISBN.isbn.ilike(f"%{normalized}%")))
            )
        stmt = stmt.where(or_(*conditions))

    books = db.scalars(stmt).unique().all()
    today = date.today()
    data = []
    for book in books:
        loan = active_loan(book)
        if loan and loan.due_date and loan.due_date < today:
            status = "ZAMUJA"
        elif loan:
            status = "POSOJENA"
        else:
            status = "NA VOLJO"
        authors = ", ".join(
            item.author.name for item in sorted(book.authors, key=lambda item: item.position)
            if item.author
        )
        isbns = ", ".join(item.isbn for item in book.isbns)
        location_path = " · ".join(
            value for value in (
                book.location.name if book.location else "",
                book.room.name if book.room else "",
                book.cabinet.name if book.cabinet else "",
                book.shelf.name if book.shelf else "",
            ) if value
        )
        data.append({
            "book": book,
            "loan": loan,
            "authors": authors,
            "isbns": isbns,
            "genre_name": book.genre.name if book.genre else "",
            "collection_name": book.collection.name if book.collection else "",
            "location_path": location_path or "Lokacija ni določena",
            "status": status,
        })
    return data


BOOK_SORT_FIELDS = {
    "inventory_no": "Inventarna številka",
    "title": "Naslov",
    "authors": "Avtorji",
    "year": "Leto",
    "isbns": "ISBN",
    "genre": "Žanr",
    "collection": "Zbirka",
    "location": "Lokacija",
    "condition": "Stanje knjige",
    "status": "Status",
}


def _sort_book_rows(rows, sort: str, direction: str):
    if sort not in BOOK_SORT_FIELDS:
        sort = "title"
    reverse = direction == "desc"

    def value_for(row):
        book = row["book"]
        values = {
            "inventory_no": book.inventory_no or "",
            "title": book.title or "",
            "authors": row["authors"],
            "year": book.year,
            "isbns": row["isbns"],
            "genre": row["genre_name"],
            "collection": row["collection_name"],
            "location": row["location_path"],
            "condition": book.condition or "",
            "status": row["status"],
        }
        return values[sort]

    rows.sort(
        key=lambda row: value_for(row).casefold() if isinstance(value_for(row), str) else (value_for(row) or 0),
        reverse=reverse,
    )
    # Stable final pass keeps blank values at the bottom for both sort directions.
    rows.sort(key=lambda row: value_for(row) is None or value_for(row) == "")
    return rows, sort


def _listing_urls(q: str, sort: str, direction: str, view: str):
    base = {"q": q, "sort": sort, "direction": direction}
    view_urls = {
        name: "/books?" + urlencode({**base, "view": name})
        for name in ("cards", "list")
    }
    sort_urls = {}
    for field in BOOK_SORT_FIELDS:
        next_direction = "desc" if sort == field and direction == "asc" else "asc"
        sort_urls[field] = "/books?" + urlencode({**base, "sort": field, "direction": next_direction, "view": view})
    export_url = "/books/export.xlsx?" + urlencode({"q": q, "sort": sort, "direction": direction})
    return view_urls, sort_urls, export_url


@router.get("/books", response_class=HTMLResponse)
def books(
    request: Request, q: str = "", sort: str = "title", direction: str = "asc",
    view: str = "cards", db: Session = Depends(get_db),
):
    view = view if view in ("cards", "list") else "cards"
    direction = direction if direction in ("asc", "desc") else "asc"
    data = _book_listing_rows(db, q)
    for row in data:
        row["can_manage"] = is_admin(request) or row["book"].location_id in allowed_location_ids(request)
    data, sort = _sort_book_rows(data, sort, direction)
    view_urls, sort_urls, export_url = _listing_urls(q, sort, direction, view)
    return render(
        request, "books.html", rows=data, q=q, today=date.today(),
        sort=sort, direction=direction, view=view,
        view_urls=view_urls, sort_urls=sort_urls, export_url=export_url,
        result_count=len(data),
    )


def _excel_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


@router.get("/books/export.xlsx")
def export_books_xlsx(
    request: Request, q: str = "", sort: str = "title", direction: str = "asc",
    db: Session = Depends(get_db),
):
    direction = direction if direction in ("asc", "desc") else "asc"
    data = _book_listing_rows(db, q)
    data, sort = _sort_book_rows(data, sort, direction)

    wb = Workbook()
    ws = wb.active
    ws.title = "Knjige"
    headers = [
        "Inventarna številka", "Naslov", "Avtorji", "Leto", "ISBN", "Žanr",
        "Zbirka", "Lokacija", "Stanje knjige", "Status",
    ]
    ws.append(headers)
    for item in data:
        book = item["book"]
        ws.append([
            _excel_safe(book.inventory_no), _excel_safe(book.title), _excel_safe(item["authors"]),
            book.year, _excel_safe(item["isbns"]), _excel_safe(item["genre_name"]),
            _excel_safe(item["collection_name"]), _excel_safe(item["location_path"]),
            _excel_safe(book.condition), _excel_safe(item["status"]),
        ])
    header_fill = PatternFill("solid", fgColor="416B9C")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    widths = [20, 42, 34, 10, 24, 20, 22, 48, 18, 16]
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + index)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"knjiznica_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/books/new", response_class=HTMLResponse)
def new_book(request: Request, db: Session = Depends(get_db)):
    return render(
        request, "book_form.html",
        **book_form_context(db, location_id=current_location_id(request)),
    )


@router.post("/books/save")
async def save_book(
    request: Request, id: int = Form(0), inventory_no: str = Form(""), title: str = Form(...),
    subtitle: str = Form(""), authors: str = Form(""), year: str = Form(""),
    publisher: str = Form(""), publication_place: str = Form(""), language: str = Form(""),
    genre: str = Form(""), collection: str = Form(""), isbns: str = Form(""),
    room_id: int = Form(0), cabinet_id: int = Form(0), shelf_id: int = Form(0),
    special_edition: str = Form(""), condition: str = Form(""), summary: str = Form(""),
    special_note: str = Form(""), acquisition_date: str = Form(""), purchase_price: str = Form(""),
    acquisition_source: str = Form(""), cover_file: UploadFile | None = File(None),
    cover_source_url: str = Form(""), allow_duplicate: str = Form("0"),
    db: Session = Depends(get_db),
):
    book = db.get(Book, id) if id else Book(
        inventory_no="", location_id=current_location_id(request)
    )
    if not book:
        raise HTTPException(404, "Knjiga ne obstaja.")
    require_location(request, book.location_id)

    if not id and allow_duplicate != "1":
        values = {clean_isbn(value) for value in isbns.replace(";", ",").split(",")}
        values.discard("")
        if values:
            duplicate = db.scalar(
                select(BookISBN).where(BookISBN.isbn.in_(values)).limit(1)
            )
            if duplicate:
                return RedirectResponse("/books/new?duplicate=1", status_code=303)

    if not id:
        book.inventory_no = inventory_no.strip() or new_inventory_no(db)
    elif inventory_no.strip():
        book.inventory_no = inventory_no.strip()

    book.title = title.strip()
    book.subtitle = subtitle.strip() or None
    book.year = int(year) if year.strip().isdigit() else None
    book.publisher = publisher.strip() or None
    book.publication_place = publication_place.strip() or None
    book.language = language.strip() or None
    book.special_edition = special_edition.lower() in ("1", "da", "true", "on")
    book.condition = condition.strip() or None
    book.summary = summary.strip() or None
    book.special_note = special_note.strip() or None
    book.purchase_price = purchase_price.strip() or None
    book.acquisition_source = acquisition_source.strip() or None
    book.acquisition_date = date_value(acquisition_date)
    book.genre = ensure_named(db, Genre, genre)
    book.collection = ensure_named(db, Collection, collection)

    room_obj = db.get(Room, room_id) if room_id else None
    cabinet_obj = db.get(Cabinet, cabinet_id) if cabinet_id else None
    shelf_obj = db.get(Shelf, shelf_id) if shelf_id else None
    if room_obj and room_obj.location_id != book.location_id:
        room_obj = None
    if cabinet_obj and cabinet_obj.room.location_id != book.location_id:
        cabinet_obj = None
    if shelf_obj and shelf_obj.cabinet.room.location_id != book.location_id:
        shelf_obj = None
    if cabinet_obj and (not room_obj or cabinet_obj.room_id != room_obj.id):
        cabinet_obj = None
    if shelf_obj and (not cabinet_obj or shelf_obj.cabinet_id != cabinet_obj.id):
        shelf_obj = None
    book.room, book.cabinet, book.shelf = room_obj, cabinet_obj, shelf_obj

    if not id:
        db.add(book)
    db.flush()
    set_authors(db, book, authors)
    set_isbns(db, book, isbns)

    cover_notice = ""
    if cover_file and cover_file.filename:
        data = await cover_file.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(400, "Slika je prevelika (največ 8 MB).")
        path = save_uploaded_cover(data, book.id, db)
        if not path:
            raise HTTPException(400, "Datoteka ni veljavna slika. Uporabi JPG, PNG ali WEBP.")
        book.cover_path = path
    elif cover_source_url.strip():
        try:
            path = await save_cover(cover_source_url.strip(), book.id, db)
        except Exception:
            path = None
        if path:
            book.cover_path = path
            cover_notice = "?cover_saved=1"
        else:
            cover_notice = "?cover_error=1"

    db.commit()
    destination = f"/books/{book.id}/edit{cover_notice}" if cover_notice else f"/books/{book.id}"
    return RedirectResponse(destination, status_code=303)


@router.get("/covers/{book_id}")
def cover_image(book_id: int, db: Session = Depends(get_db)):
    cover = db.get(CoverImage, book_id)
    if not cover:
        raise HTTPException(404, "Naslovnica ni na voljo.")
    return Response(
        content=cover.image_data,
        media_type=cover.mime_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{cover.book_id}-{cover.file_size}-{cover.updated_at.timestamp():.0f}"',
        },
    )


@router.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(404, "Knjiga ni najdena.")

    can_manage = is_admin(request) or book.location_id in allowed_location_ids(request)
    borrower_rows = (
        db.scalars(
            select(Borrower)
            .where(Borrower.location_id == book.location_id)
            .order_by(Borrower.last_name, Borrower.first_name)
        ).all()
        if can_manage else []
    )

    # Ciljne knjižnice so samo tiste, do katerih ima uporabnik dostop.
    if is_admin(request):
        location_stmt = select(Location).where(Location.active.is_(True))
    else:
        permitted_ids = allowed_location_ids(request)
        location_stmt = select(Location).where(
            Location.active.is_(True), Location.id.in_(permitted_ids)
        )
    location_rows = db.scalars(location_stmt.order_by(Location.name)).all()

    return render(
        request, "book_detail.html",
        book=book, loan=active_loan(book), borrowers=borrower_rows,
        can_manage_book=can_manage, today=date.today(),
        default_due_date=(date.today() + timedelta(days=30)).isoformat(),
        available_locations=location_rows,
    )


@router.post("/books/{book_id}/move")
def move_book(
    book_id: int, request: Request, target_location_id: int = Form(...),
    db: Session = Depends(get_db),
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Knjiga ne obstaja.")
    require_location(request, book.location_id)

    target = db.get(Location, target_location_id)
    if not target or not target.active:
        raise HTTPException(400, "Ciljna knjižnica ne obstaja ali ni aktivna.")

    permitted_ids = allowed_location_ids(request)
    if not is_admin(request) and target.id not in permitted_ids:
        raise HTTPException(403, "Za ciljno knjižnico nimaš pravic.")

    if target.id == book.location_id:
        return RedirectResponse(f"/books/{book.id}", status_code=303)

    if active_loan(book):
        return RedirectResponse(
            f"/books/{book.id}?move_error=loan", status_code=303
        )

    try:
        book.location_id = target.id
        # Soba/omara/polica pripadajo izvorni knjižnici, zato jih ob prenosu počistimo.
        book.room_id = None
        book.cabinet_id = None
        book.shelf_id = None
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            f"/books/{book.id}?move_error=database", status_code=303
        )

    return RedirectResponse(f"/books/{book.id}?moved=1", status_code=303)


@router.get("/books/{book_id}/edit", response_class=HTMLResponse)
def edit_book(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(404)
    require_location(request, book.location_id)
    return render(request, "book_form.html", **book_form_context(db, book))


@router.post("/books/{book_id}/delete")
def delete_book(book_id: int, request: Request, db: Session = Depends(get_db)):
    """Permanently remove one book and its book-specific history.

    This is a private home library: loan and reading history belonging to the
    deleted physical copy is deleted as well. Borrowers, family members,
    authors, and other books are retained.
    """
    book = db.get(Book, book_id)
    if not book:
        return RedirectResponse("/books", status_code=303)

    require_location(request, book.location_id)

    try:
        # Delete dependants explicitly. This also works with MariaDB tables
        # whose foreign-key constraints were created before ON DELETE CASCADE
        # was added to the SQLAlchemy model. Keep all statements in one
        # transaction so a failure rolls the complete operation back.
        db.execute(delete(Loan).where(Loan.book_id == book_id))
        db.execute(delete(ReadingRecord).where(ReadingRecord.book_id == book_id))
        db.execute(delete(BookAuthor).where(BookAuthor.book_id == book_id))
        db.execute(delete(BookISBN).where(BookISBN.book_id == book_id))
        db.execute(delete(CoverImage).where(CoverImage.book_id == book_id))

        result = db.execute(delete(Book).where(Book.id == book_id))
        if result.rowcount != 1:
            raise RuntimeError(f"Brisanje knjige {book_id}: pričakovana 1 vrstica, izbrisano {result.rowcount}.")

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Brisanje knjige ni uspelo (book_id=%s).", book_id)
        return RedirectResponse(
            f"/books/{book_id}?delete_error=database", status_code=303
        )

    return RedirectResponse("/books?deleted=1", status_code=303)


@router.get("/lookup", response_class=HTMLResponse)
async def lookup(
    request: Request, q: str = "", target_book_id: int = 0,
    return_to: str = "/books/new", db: Session = Depends(get_db),
):
    results = await lookup_book(q) if q else []
    target_book = db.get(Book, target_book_id) if target_book_id else None
    if target_book_id and not target_book:
        raise HTTPException(404, "Knjiga ni najdena.")
    if target_book:
        safe_return = f"/books/{target_book.id}/edit"
    elif return_to == "/books/new" or re.fullmatch(r"/books/\d+/edit", return_to or ""):
        safe_return = return_to
    else:
        safe_return = "/books/new"
    emka_url = f"https://emka.si/search?q={quote_plus(q)}&type=product" if q else "https://emka.si"
    cobiss_url = (
        f"https://plus.cobiss.net/cobiss/si/sl/bib/search?q={quote_plus(q)}"
        if q else "https://plus.cobiss.net/cobiss/si/sl/bib/search"
    )
    return render(
        request, "lookup.html", q=q, results=results, target_book=target_book,
        return_to=safe_return, emka_url=emka_url, cobiss_url=cobiss_url,
    )


@router.post("/lookup/save")
async def lookup_save(
    request: Request, title: str = Form(...), subtitle: str = Form(""), authors: str = Form(""),
    year: str = Form(""), publisher: str = Form(""), language: str = Form(""),
    isbns: str = Form(""), cover: str = Form(""), description: str = Form(""),
    publication_place: str = Form(""), collection: str = Form(""),
    db: Session = Depends(get_db),
):
    book = Book(
        location_id=current_location_id(request), inventory_no=new_inventory_no(db),
        title=title.strip(), subtitle=subtitle or None,
        year=int(year[:4]) if year[:4].isdigit() else None,
        publisher=publisher or None, publication_place=publication_place or None,
        language=language or None, summary=description or None,
        collection=ensure_named(db, Collection, collection),
    )
    db.add(book)
    db.flush()
    set_authors(db, book, authors)
    set_isbns(db, book, isbns)

    cover_saved = False
    if cover:
        try:
            book.cover_path = await save_cover(cover, book.id, db)
            cover_saved = bool(book.cover_path)
        except Exception:
            book.cover_path = None
    db.commit()
    suffix = "?cover_saved=1" if cover_saved else ("?cover_error=1" if cover else "")
    return RedirectResponse(f"/books/{book.id}/edit{suffix}", status_code=303)


@router.post("/books/{book_id}/cover/save")
async def book_cover_save(
    book_id: int, request: Request, cover: str = Form(""),
    db: Session = Depends(get_db),
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404)
    require_location(request, book.location_id)
    try:
        path = await save_cover(cover, book.id, db)
    except Exception:
        path = None
    if path:
        book.cover_path = path
        db.commit()
        return RedirectResponse(f"/books/{book_id}/edit?cover_saved=1", status_code=303)
    return RedirectResponse(f"/books/{book_id}/edit?cover_error=1", status_code=303)
