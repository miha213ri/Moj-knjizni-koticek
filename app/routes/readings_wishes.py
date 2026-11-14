from datetime import date
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.models import Book, FamilyMember, ReadingRecord, Wishlist, Genre
from app.services import clean_isbn, new_inventory_no, set_authors, set_isbns
from app.route_helpers import render, date_value, redirect_notice
from app.access import current_location_id, member_filter_id, is_admin, require_admin

router = APIRouter()

@router.get("/readings", response_class=HTMLResponse)
def readings(
    request: Request, q: str = "", sort: str = "finish_date", direction: str = "desc",
    db: Session = Depends(get_db),
):
    sort_map = {
        "book": Book.title, "member": FamilyMember.name,
        "start_date": ReadingRecord.start_date, "finish_date": ReadingRecord.finish_date,
        "rating": ReadingRecord.rating, "comment": ReadingRecord.comment,
    }
    sort_column = sort_map.get(sort, ReadingRecord.finish_date)
    own_member_id = member_filter_id(request)
    stmt = select(ReadingRecord).outerjoin(Book).join(FamilyMember).options(
        selectinload(ReadingRecord.book), selectinload(ReadingRecord.member),
    )
    if own_member_id:
        stmt = stmt.where(ReadingRecord.member_id == own_member_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Book.title.ilike(like), ReadingRecord.external_title.ilike(like),
                              FamilyMember.name.ilike(like), ReadingRecord.comment.ilike(like)))
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = db.scalars(stmt.order_by(ordering, Book.title)).all()
    return render(
        request, "readings.html", rows=rows,
        books=db.scalars(select(Book).order_by(Book.title)).all(),
        members=([db.get(FamilyMember, own_member_id)] if own_member_id else
                 db.scalars(select(FamilyMember).order_by(FamilyMember.name)).all()),
        q=q, sort=sort, direction=direction,
    )

@router.post("/family/save")
def family_save(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request)
    name = name.strip()
    if name and not any(item.name.casefold() == name.casefold() for item in db.scalars(select(FamilyMember)).all()):
        db.add(FamilyMember(name=name, location_id=current_location_id(request)))
        db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.post("/family/{member_id}/save")
def family_update(member_id: int, request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request)
    member = db.get(FamilyMember, member_id)
    if not member:
        raise HTTPException(404)
    name = name.strip()
    duplicate = any(item.id != member_id and item.name.casefold() == name.casefold()
                    for item in db.scalars(select(FamilyMember)).all())
    if not name or duplicate:
        return redirect_notice("/readings", "Ime družinskega člana ne sme biti prazno ali podvojeno.")
    member.name = name
    db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.post("/family/{member_id}/delete")
def family_delete(member_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    member = db.get(FamilyMember, member_id)
    if member:
        used_reading = db.scalar(select(ReadingRecord.id).where(ReadingRecord.member_id == member_id).limit(1))
        used_wish = db.scalar(select(Wishlist.id).where(Wishlist.member_id == member_id).limit(1))
        if used_reading or used_wish:
            return redirect_notice("/readings", "Družinskega člana ni mogoče izbrisati, ker ima zapise branja ali knjižne želje. Lahko pa ga preimenuješ.")
        db.delete(member)
        db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.post("/readings/save")
def reading_save(
    request: Request, book_id: int = Form(0), book_title: str = Form(""), member_id: int = Form(...),
    start_date: str = Form(""), finish_date: str = Form(""), rating: str = Form(""),
    comment: str = Form(""), db: Session = Depends(get_db),
):
    finish, start = date_value(finish_date), date_value(start_date)
    own_member_id = member_filter_id(request)
    if own_member_id:
        member_id = own_member_id
    if start and finish and finish < start:
        return redirect_notice("/readings", "Datum zaključka ne sme biti pred datumom začetka.")
    selected_book = db.get(Book, book_id) if book_id else None
    external_title = None if selected_book else book_title.strip()
    if not selected_book and not external_title:
        return redirect_notice("/readings", "Vnesi naslov knjige ali izberi predlagano knjigo iz domače knjižnice.")
    db.add(ReadingRecord(book_id=selected_book.id if selected_book else None, external_title=external_title,
                         member_id=member_id, start_date=start, finish_date=finish,
                         rating=int(rating) if rating.isdigit() and 1 <= int(rating) <= 5 else None,
                         comment=comment.strip() or None, completed=bool(finish)))
    db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.post("/readings/{record_id}/save")
def reading_update(
    record_id: int, request: Request, book_id: int = Form(0), book_title: str = Form(""),
    member_id: int = Form(...), start_date: str = Form(""), finish_date: str = Form(""),
    rating: str = Form(""), comment: str = Form(""), db: Session = Depends(get_db),
):
    record = db.get(ReadingRecord, record_id)
    if not record:
        raise HTTPException(404)
    own_member_id = member_filter_id(request)
    if own_member_id and record.member_id != own_member_id:
        raise HTTPException(403)
    if own_member_id:
        member_id = own_member_id
    start, finish = date_value(start_date), date_value(finish_date)
    if start and finish and finish < start:
        return redirect_notice("/readings", "Datum zaključka ne sme biti pred datumom začetka.")
    selected_book = db.get(Book, book_id) if book_id else None
    external_title = None if selected_book else book_title.strip()
    if not selected_book and not external_title:
        return redirect_notice("/readings", "Vnesi naslov knjige ali izberi predlagano knjigo iz domače knjižnice.")
    record.book_id = selected_book.id if selected_book else None
    record.external_title = external_title
    record.member_id = member_id
    record.start_date, record.finish_date = start, finish
    record.rating = int(rating) if rating.isdigit() and 1 <= int(rating) <= 5 else None
    record.comment, record.completed = comment.strip() or None, bool(finish)
    db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.post("/readings/{record_id}/delete")
def reading_delete(record_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.get(ReadingRecord, record_id)
    if record:
        own_member_id = member_filter_id(request)
        if own_member_id and record.member_id != own_member_id:
            raise HTTPException(403)
        db.delete(record)
        db.commit()
    return RedirectResponse("/readings", status_code=303)

@router.get("/wishes", response_class=HTMLResponse)
def wishes(request: Request, q: str = "", sort: str = "priority", direction: str = "asc", db: Session = Depends(get_db)):
    sort_map = {
        "title": Wishlist.title, "author": Wishlist.author, "member": FamilyMember.name,
        "priority": Wishlist.priority, "status": Wishlist.status, "isbn": Wishlist.isbn,
    }
    sort_column = sort_map.get(sort, Wishlist.priority)
    own_member_id = member_filter_id(request)
    stmt = select(Wishlist).join(FamilyMember).options(
        selectinload(Wishlist.member), selectinload(Wishlist.genre),
    )
    if own_member_id:
        stmt = stmt.where(Wishlist.member_id == own_member_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Wishlist.title.ilike(like), Wishlist.author.ilike(like),
                              Wishlist.isbn.ilike(like), Wishlist.status.ilike(like),
                              Wishlist.priority.ilike(like), Wishlist.note.ilike(like),
                              FamilyMember.name.ilike(like)))
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = db.scalars(stmt.order_by(ordering, Wishlist.title)).all()
    return render(request, "wishes.html", rows=rows,
                  members=([db.get(FamilyMember, own_member_id)] if own_member_id else
                           db.scalars(select(FamilyMember).order_by(FamilyMember.name)).all()),
                  q=q, sort=sort, direction=direction)

@router.post("/wishes/save")
def wish_save(
    request: Request, member_id: int = Form(...), title: str = Form(...), author: str = Form(""),
    isbn: str = Form(""), priority: str = Form("Srednja"), status: str = Form("Želja"),
    url: str = Form(""), note: str = Form(""), db: Session = Depends(get_db),
):
    own_member_id = member_filter_id(request)
    member_id = own_member_id or member_id
    db.add(Wishlist(member_id=member_id, title=title.strip(), author=author.strip() or None,
                    isbn=clean_isbn(isbn) or None, priority=priority, status=status,
                    url=url.strip() or None, note=note.strip() or None))
    db.commit()
    return RedirectResponse("/wishes", status_code=303)

@router.post("/wishes/{wish_id}/save")
def wish_update(
    wish_id: int, request: Request, member_id: int = Form(...), title: str = Form(...), author: str = Form(""),
    isbn: str = Form(""), priority: str = Form("Srednja"), status: str = Form("Želja"),
    url: str = Form(""), note: str = Form(""), db: Session = Depends(get_db),
):
    wish = db.get(Wishlist, wish_id)
    if not wish:
        raise HTTPException(404)
    own_member_id = member_filter_id(request)
    if own_member_id and wish.member_id != own_member_id:
        raise HTTPException(403)
    wish.member_id, wish.title = own_member_id or member_id, title.strip()
    wish.author, wish.isbn = author.strip() or None, clean_isbn(isbn) or None
    wish.priority, wish.status = priority, status
    wish.url, wish.note = url.strip() or None, note.strip() or None
    db.commit()
    return RedirectResponse("/wishes", status_code=303)

@router.post("/wishes/{wish_id}/delete")
def wish_delete(wish_id: int, request: Request, db: Session = Depends(get_db)):
    wish = db.get(Wishlist, wish_id)
    if wish:
        own_member_id = member_filter_id(request)
        if own_member_id and wish.member_id != own_member_id:
            raise HTTPException(403)
        db.delete(wish)
        db.commit()
    return RedirectResponse("/wishes", status_code=303)

@router.post("/wishes/{wish_id}/add-book")
def wish_add_book(wish_id: int, request: Request, db: Session = Depends(get_db)):
    wish = db.get(Wishlist, wish_id)
    if not wish:
        raise HTTPException(404)
    own_member_id = member_filter_id(request)
    if own_member_id and wish.member_id != own_member_id:
        raise HTTPException(403)
    book = Book(location_id=current_location_id(request), inventory_no=new_inventory_no(db), title=wish.title, genre_id=wish.genre_id)
    db.add(book)
    db.flush()
    if wish.author:
        set_authors(db, book, wish.author)
    if wish.isbn:
        set_isbns(db, book, wish.isbn)
    wish.status = "Že v knjižnici"
    db.commit()
    return RedirectResponse(f"/books/{book.id}/edit", status_code=303)

