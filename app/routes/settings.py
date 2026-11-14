from datetime import date
from io import BytesIO
from pathlib import Path
import logging
from collections import defaultdict
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import Book, BookISBN, CoverImage, Cabinet, Collection, FamilyMember, Genre, Loan, ReadingRecord, Room, Shelf, Wishlist, Location, User, Borrower
from app.services import ensure_named, find_named, clean_isbn, save_uploaded_cover
from app.import_export import template_bytes, import_xlsx, log_import_error
from app.route_helpers import render, redirect_notice
from app.access import current_location_id, member_filter_id, is_admin, require_admin, require_location

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/stats", response_class=HTMLResponse)
def stats(request: Request, db: Session = Depends(get_db)):
    location_id = current_location_id(request)
    total = db.query(Book).filter(Book.location_id == location_id).count()
    on_loan = db.query(Loan).join(Book).filter(Book.location_id == location_id, Loan.returned_date.is_(None)).count()
    overdue = db.query(Loan).join(Book).filter(Book.location_id == location_id, Loan.returned_date.is_(None), Loan.due_date < date.today()).count()
    read_count = db.query(ReadingRecord).join(FamilyMember).filter(FamilyMember.location_id == location_id, ReadingRecord.completed.is_(True)).count()
    wish_count = db.query(Wishlist).join(FamilyMember).filter(FamilyMember.location_id == location_id).count()
    genres = db.query(Genre.name, func.count(Book.id)).outerjoin(Book, Book.genre_id == Genre.id).filter(Book.location_id == location_id).group_by(Genre.name).all()
    return render(request, "stats.html", total=total, on_loan=on_loan, overdue=overdue,
                  available=total - on_loan, read_count=read_count, wish_count=wish_count, genres=genres)

@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request, db: Session = Depends(get_db)):
    location_id = current_location_id(request)
    genres = db.scalars(select(Genre).order_by(Genre.name)).all()
    collections = db.scalars(select(Collection).order_by(Collection.name)).all()
    rooms = db.scalars(select(Room).where(Room.location_id == location_id).order_by(Room.name)).all()
    cabinets = db.scalars(select(Cabinet).join(Room).where(Room.location_id == location_id).options(selectinload(Cabinet.room)).order_by(Cabinet.room_id, Cabinet.name)).all()
    shelves = db.scalars(select(Shelf).join(Cabinet).join(Room).where(Room.location_id == location_id).options(selectinload(Shelf.cabinet).selectinload(Cabinet.room)).order_by(Shelf.cabinet_id, Shelf.name)).all()
    members = db.scalars(select(FamilyMember).where(FamilyMember.location_id == location_id).order_by(FamilyMember.name)).all()
    sections = [
        {"kind": "genre", "label": "Žanri", "items": genres},
        {"kind": "collection", "label": "Zbirke", "items": collections},
        {"kind": "room", "label": "Sobe", "items": rooms},
        {"kind": "cabinet", "label": "Omare", "items": cabinets},
        {"kind": "shelf", "label": "Police", "items": shelves},
    ]
    return render(request, "settings.html", genres=genres, collections=collections, rooms=rooms,
                  cabinets=cabinets, shelves=shelves, members=members, sections=sections)

@router.post("/settings/add")
def settings_add(
    request: Request, kind: str = Form(...), name: str = Form(...), room_id: int = Form(0),
    cabinet_id: int = Form(0), db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/settings", status_code=303)
    if kind in ("genre", "collection"):
        require_admin(request)
        model = {"genre": Genre, "collection": Collection}[kind]
        ensure_named(db, model, name)
    elif kind == "room":
        location_id = current_location_id(request)
        duplicate = db.scalar(select(Room.id).where(Room.location_id == location_id, Room.name == name))
        if not duplicate:
            db.add(Room(location_id=location_id, name=name))
    elif kind == "cabinet" and room_id:
        room = db.get(Room, room_id)
        if room and room.location_id == current_location_id(request) and not find_named(db, Cabinet, name, parent_field=Cabinet.room_id, parent_id=room_id):
            db.add(Cabinet(room_id=room_id, name=name))
    elif kind == "shelf" and cabinet_id:
        cabinet = db.get(Cabinet, cabinet_id)
        if cabinet and cabinet.room.location_id == current_location_id(request) and not find_named(db, Shelf, name, parent_field=Shelf.cabinet_id, parent_id=cabinet_id):
            db.add(Shelf(cabinet_id=cabinet_id, name=name))
    db.commit()
    return RedirectResponse("/settings", status_code=303)

@router.post("/settings/{kind}/{item_id}/save")
def settings_update(
    kind: str, item_id: int, request: Request, name: str = Form(...), room_id: int = Form(0),
    cabinet_id: int = Form(0), db: Session = Depends(get_db),
):
    model_map = {"genre": Genre, "collection": Collection, "room": Room, "cabinet": Cabinet, "shelf": Shelf}
    model = model_map.get(kind)
    if not model:
        raise HTTPException(404)
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(404)
    if kind == "room":
        require_location(request, item.location_id)
    elif kind in ("cabinet", "shelf"):
        parent_location = item.room.location_id if kind == "cabinet" else item.cabinet.room.location_id
        require_location(request, parent_location)
    name = name.strip()
    if not name:
        return redirect_notice("/settings", "Ime ne sme biti prazno.")
    if kind in ("genre", "collection"):
        require_admin(request)
        duplicate = find_named(db, model, name, exclude_id=item_id)
    elif kind == "room":
        require_location(request, item.location_id)
        duplicate = db.scalar(select(Room.id).where(Room.location_id == item.location_id, Room.name == name, Room.id != item_id))
    elif kind == "cabinet":
        duplicate = find_named(db, model, name, parent_field=Cabinet.room_id, parent_id=room_id, exclude_id=item_id)
    elif kind == "shelf":
        duplicate = find_named(db, model, name, parent_field=Shelf.cabinet_id, parent_id=cabinet_id, exclude_id=item_id)
    else:
        duplicate = None
    if duplicate:
        return redirect_notice("/settings", "Vnos s tem imenom že obstaja.")
    item.name = name
    if kind == "cabinet":
        parent_room = db.get(Room, room_id)
        if not parent_room or parent_room.location_id != current_location_id(request):
            return redirect_notice("/settings", "Omari moraš določiti sobo iz aktivne lokacije.")
        if duplicate:
            return redirect_notice("/settings", "Takšna omara v tej sobi že obstaja.")
        item.room_id = room_id
    elif kind == "shelf":
        parent_cabinet = db.get(Cabinet, cabinet_id)
        if not parent_cabinet or parent_cabinet.room.location_id != current_location_id(request):
            return redirect_notice("/settings", "Polici moraš določiti omaro iz aktivne lokacije.")
        if duplicate:
            return redirect_notice("/settings", "Takšna polica v tej omari že obstaja.")
        item.cabinet_id = cabinet_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect_notice("/settings", "Podvojeno ime ali lokacija ni dovoljena.")
    return RedirectResponse("/settings", status_code=303)

@router.post("/settings/{kind}/{item_id}/delete")
def settings_delete(kind: str, item_id: int, request: Request, db: Session = Depends(get_db)):
    model_map = {"genre": Genre, "collection": Collection, "room": Room, "cabinet": Cabinet, "shelf": Shelf}
    model = model_map.get(kind)
    if not model:
        raise HTTPException(404)
    item = db.get(model, item_id)
    if not item:
        return RedirectResponse("/settings", status_code=303)
    if kind in ("genre", "collection"):
        require_admin(request)
    elif kind == "room":
        require_location(request, item.location_id)
    elif kind == "cabinet":
        require_location(request, item.room.location_id)
    elif kind == "shelf":
        require_location(request, item.cabinet.room.location_id)
    checks = {
        "genre": db.scalar(select(Book.id).where(Book.genre_id == item_id).limit(1)) or db.scalar(select(Wishlist.id).where(Wishlist.genre_id == item_id).limit(1)),
        "collection": db.scalar(select(Book.id).where(Book.collection_id == item_id).limit(1)),
        "room": db.scalar(select(Book.id).where(Book.room_id == item_id).limit(1)) or db.scalar(select(Cabinet.id).where(Cabinet.room_id == item_id).limit(1)),
        "cabinet": db.scalar(select(Book.id).where(Book.cabinet_id == item_id).limit(1)) or db.scalar(select(Shelf.id).where(Shelf.cabinet_id == item_id).limit(1)),
        "shelf": db.scalar(select(Book.id).where(Book.shelf_id == item_id).limit(1)),
    }
    if checks[kind]:
        labels = {"genre": "žanr", "collection": "zbirke", "room": "sobe", "cabinet": "omare", "shelf": "police"}
        return redirect_notice("/settings", f"Tega vnosa ni mogoče izbrisati, ker je že uporabljen pri knjigi ali podrejeni lokaciji. Najprej ga odstrani iz uporabe.")
    db.delete(item)
    db.commit()
    return RedirectResponse("/settings", status_code=303)

@router.get("/import/template")
def import_template():
    return StreamingResponse(BytesIO(template_bytes()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="predloga_knjige.xlsx"'})

@router.post("/import/xlsx")
async def import_books(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = file.filename or "(brez imena)"
    try:
        if not file.filename or not file.filename.lower().endswith(".xlsx"):
            raise HTTPException(400, "Naloži datoteko .xlsx.")
        content = await file.read()
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(400, "Datoteka je prevelika (največ 15 MB).")

        log_import_error(
            f"Prejet zahtevek za uvoz: datoteka={filename!r}, velikost={len(content)} B"
        )
        count, errors = import_xlsx(db, content, current_location_id(request))
        log_import_error(
            f"Endpoint uvoza zaključen: datoteka={filename!r}, uspešno={count}, napake={len(errors)}"
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_import_error(
            f"Napaka v endpointu uvoza: datoteka={filename!r}.", exc
        )
        logger.exception("Neuspešen uvoz Excelove datoteke %r", filename)
        raise HTTPException(
            500,
            "Pri uvozu Excela je prišlo do nepredvidene napake. Dogodek je zabeležen v tmp/import_xlsx.log.",
        )
    return RedirectResponse(f"/settings?imported={count}&errors={len(errors)}", status_code=303)


COVER_BULK_MAX_FILES = 50
COVER_BULK_MAX_FILE_BYTES = 8 * 1024 * 1024
COVER_BULK_MAX_TOTAL_BYTES = 40 * 1024 * 1024
COVER_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _match_cover_filename(db: Session, filename: str, location_id: int):
    """Match a cover only by an exact inventory number or a unique exact ISBN."""
    stem = Path(filename or "").stem.strip()
    folded = stem.casefold()
    for prefix in ("inventarna_", "inventarna-", "inv_", "inv-", "cover_", "cover-", "naslovnica_", "naslovnica-"):
        if folded.startswith(prefix):
            stem = stem[len(prefix):].strip()
            folded = stem.casefold()
            break

    # Inventory number has priority over ISBN because it identifies one physical copy.
    inventory_matches = db.scalars(
        select(Book).where(Book.location_id == location_id, func.lower(Book.inventory_no) == folded).limit(2)
    ).all() if stem else []
    if len(inventory_matches) == 1:
        return "matched", inventory_matches[0], "inventarna številka"
    if len(inventory_matches) > 1:
        return "ambiguous", None, "inventarna številka ni enolična"

    isbn_stem = stem
    if isbn_stem.casefold().startswith("isbn"):
        isbn_stem = isbn_stem[4:].lstrip(" _-")
    normalized = clean_isbn(isbn_stem)
    if len(normalized) in (10, 13) and normalized[:-1].isdigit() and (normalized[-1].isdigit() or normalized[-1] == "X"):
        matches = db.scalars(
            select(Book).join(BookISBN, BookISBN.book_id == Book.id)
            .where(Book.location_id == location_id, BookISBN.isbn == normalized)
            .distinct()
        ).all()
        if len(matches) == 1:
            return "matched", matches[0], "ISBN"
        if len(matches) > 1:
            return "ambiguous", None, f"ISBN {normalized} pripada več fizičnim izvodom"
        return "unmatched", None, f"ISBN {normalized} ni najden v izbrani knjižnici"

    return "unmatched", None, "ime datoteke ne vsebuje natančne inventarne številke ali ISBN"


@router.post("/covers/bulk-upload", response_class=HTMLResponse)
async def bulk_upload_covers(
    request: Request,
    files: list[UploadFile] = File(...),
    overwrite: str = Form("0"),
    db: Session = Depends(get_db),
):
    location_id = current_location_id(request)
    require_location(request, location_id)
    if not files:
        raise HTTPException(400, "Izberi vsaj eno slikovno datoteko.")
    if len(files) > COVER_BULK_MAX_FILES:
        raise HTTPException(400, f"Naenkrat lahko naložiš največ {COVER_BULK_MAX_FILES} slik.")

    prepared = []
    total_bytes = 0
    for upload in files:
        filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not filename:
            continue
        extension = Path(filename).suffix.casefold()
        if extension not in COVER_ALLOWED_EXTENSIONS:
            prepared.append({"filename": filename, "data": None, "status": "invalid", "message": "Nepodprta vrsta datoteke. Uporabi JPG, PNG ali WEBP."})
            continue
        data = await upload.read(COVER_BULK_MAX_FILE_BYTES + 1)
        if len(data) > COVER_BULK_MAX_FILE_BYTES:
            prepared.append({"filename": filename, "data": None, "status": "invalid", "message": "Slika presega omejitev 8 MB."})
            continue
        total_bytes += len(data)
        if total_bytes > COVER_BULK_MAX_TOTAL_BYTES:
            raise HTTPException(413, "Skupna velikost izbranih slik presega 40 MB. Naloži jih v več sklopih.")
        status, book, match_rule = _match_cover_filename(db, filename, location_id)
        prepared.append({
            "filename": filename, "data": data, "status": status,
            "book": book, "match_rule": match_rule,
            "message": match_rule if status != "matched" else "",
        })

    # Never choose arbitrarily when two files point to the same physical book.
    matched_by_book = defaultdict(list)
    for index, item in enumerate(prepared):
        if item["status"] == "matched":
            matched_by_book[item["book"].id].append(index)
    for indexes in matched_by_book.values():
        if len(indexes) > 1:
            for index in indexes:
                prepared[index]["status"] = "ambiguous"
                prepared[index]["message"] = "Več izbranih slik ustreza isti knjigi; nobena ni samodejno pripeta. Izberi samo eno."

    results = []
    summary = {"added": 0, "replaced": 0, "existing": 0, "unmatched": 0, "ambiguous": 0, "invalid": 0}
    replace_existing = overwrite == "1"
    for item in prepared:
        result = {"filename": item["filename"], "book_title": "—", "inventory_no": "—", "status": "", "message": ""}
        status = item["status"]
        if status == "invalid":
            summary["invalid"] += 1
            result.update(status="Napaka", message=item["message"])
        elif status == "unmatched":
            summary["unmatched"] += 1
            result.update(status="Ni zadetka", message=item["message"])
        elif status == "ambiguous":
            summary["ambiguous"] += 1
            result.update(status="Dvoumno", message=item["message"])
        else:
            book = item["book"]
            result.update(book_title=book.title, inventory_no=book.inventory_no)
            existing = db.get(CoverImage, book.id) is not None
            if existing and not replace_existing:
                summary["existing"] += 1
                result.update(status="Že ima naslovnico", message="Obstoječa naslovnica je ohranjena. Če jo želiš zamenjati, ponovi uvoz z možnostjo zamenjave.")
            else:
                try:
                    path = save_uploaded_cover(item["data"], book.id, db)
                    if not path:
                        db.rollback()
                        summary["invalid"] += 1
                        result.update(status="Neveljavna slika", message="Datoteke ni bilo mogoče prepoznati kot veljavne naslovnice.")
                    else:
                        book.cover_path = path
                        db.commit()
                        if existing:
                            summary["replaced"] += 1
                            result.update(status="Zamenjana", message=f"Ujemanje po {item['match_rule']}; prejšnja naslovnica je zamenjana.")
                        else:
                            summary["added"] += 1
                            result.update(status="Dodana", message=f"Natančno ujemanje po {item['match_rule']}.")
                except Exception:
                    db.rollback()
                    logger.exception("Množični uvoz naslovnice ni uspel: %s", item["filename"])
                    summary["invalid"] += 1
                    result.update(status="Napaka pri shranjevanju", message="Shranjevanje ni uspelo. Podrobnost je zabeležena v dnevniku aplikacije.")
        results.append(result)

    return render(request, "cover_bulk_result.html", results=results, summary=summary, total=len(results))
