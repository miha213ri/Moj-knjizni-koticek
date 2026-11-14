from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Borrower, Loan
from app.route_helpers import render, redirect_notice
from app.access import current_location_id, require_location

router = APIRouter()

@router.get("/borrowers", response_class=HTMLResponse)
def borrowers(
    request: Request, q: str = "", sort: str = "last_name", direction: str = "asc",
    db: Session = Depends(get_db),
):
    sort_map = {
        "first_name": Borrower.first_name, "last_name": Borrower.last_name,
        "address": Borrower.address, "contact": Borrower.contact, "note": Borrower.note,
    }
    sort_column = sort_map.get(sort, Borrower.last_name)
    location_id = current_location_id(request)
    stmt = select(Borrower).where(Borrower.location_id == location_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Borrower.first_name.ilike(like), Borrower.last_name.ilike(like),
                              Borrower.address.ilike(like), Borrower.contact.ilike(like), Borrower.note.ilike(like)))
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = db.scalars(stmt.order_by(ordering, Borrower.first_name)).all()
    return render(request, "borrowers.html", borrowers=rows, q=q, sort=sort, direction=direction)

@router.post("/borrowers/save")
def borrower_save(
    request: Request, first_name: str = Form(...), last_name: str = Form(...), address: str = Form(""),
    contact: str = Form(""), note: str = Form(""), return_to: str = Form("/borrowers"),
    db: Session = Depends(get_db),
):
    db.add(Borrower(location_id=current_location_id(request), first_name=first_name.strip(), last_name=last_name.strip(),
                    address=address.strip() or None, contact=contact.strip() or None, note=note.strip() or None))
    db.commit()
    safe_return = return_to if return_to.startswith("/books/") else "/borrowers"
    return RedirectResponse(safe_return, status_code=303)

@router.post("/borrowers/{borrower_id}/save")
def borrower_update(
    borrower_id: int, request: Request, first_name: str = Form(...), last_name: str = Form(...),
    address: str = Form(""), contact: str = Form(""), note: str = Form(""),
    db: Session = Depends(get_db),
):
    borrower = db.get(Borrower, borrower_id)
    if not borrower:
        raise HTTPException(404)
    require_location(request, borrower.location_id)
    borrower.first_name, borrower.last_name = first_name.strip(), last_name.strip()
    borrower.address, borrower.contact, borrower.note = address.strip() or None, contact.strip() or None, note.strip() or None
    db.commit()
    return RedirectResponse("/borrowers", status_code=303)

@router.post("/borrowers/{borrower_id}/delete")
def borrower_delete(borrower_id: int, request: Request, db: Session = Depends(get_db)):
    borrower = db.get(Borrower, borrower_id)
    if borrower:
        require_location(request, borrower.location_id)
        if db.scalar(select(Loan.id).where(Loan.borrower_id == borrower_id).limit(1)):
            return redirect_notice("/borrowers", "Osebe ni mogoče izbrisati, ker ima zgodovino izposoj. Podatke lahko še vedno urediš.")
        db.delete(borrower)
        db.commit()
    return RedirectResponse("/borrowers", status_code=303)

