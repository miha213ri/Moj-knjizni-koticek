from datetime import date
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, or_, case
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Loan, Book, Borrower, BookAuthor, Author
from app.templating import render_page
from app.access import current_location_id, require_location

router = APIRouter()


def _parse_iso_date(value: str, label: str, *, required: bool = False):
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError(f"Polje '{label}' je obvezno.")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Datum '{label}' ni veljaven.") from exc


@router.get("/loans")
def loan_list(
    request: Request,
    q: str = "",
    sort: str = "loan_date",
    direction: str = "desc",
    notice: str = "",
    db: Session = Depends(get_db),
):
    sort_map = {
        "book": Book.title,
        "borrower": Borrower.last_name,
        "loan_date": Loan.loan_date,
        "due_date": Loan.due_date,
        "status": case((Loan.due_date.is_not(None) & (Loan.due_date < date.today()), 0), else_=1),
    }
    sort_column = sort_map.get(sort, Loan.loan_date)
    stmt = select(Loan).join(Book).join(Borrower).options(
        selectinload(Loan.book).selectinload(Book.authors).selectinload(BookAuthor.author),
        selectinload(Loan.borrower),
    ).where(Loan.returned_date.is_(None), Book.location_id == current_location_id(request))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Book.title.ilike(like),
            Book.inventory_no.ilike(like),
            Borrower.first_name.ilike(like),
            Borrower.last_name.ilike(like),
            Borrower.address.ilike(like),
            Borrower.contact.ilike(like),
            Loan.note.ilike(like),
        ))
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = db.scalars(stmt.order_by(ordering, Book.title)).unique().all()
    return render_page(request, "loans.html", loans=rows, q=q, sort=sort,
                       direction=direction, today=date.today(), notice=notice)


@router.post("/loans/{loan_id}/dates")
def update_loan_dates(
    loan_id: int, request: Request,
    loan_date: str = Form(...),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    loan = db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(404, "Izposoja ni najdena.")
    require_location(request, loan.book.location_id)
    try:
        new_loan_date = _parse_iso_date(loan_date, "datum izposoje", required=True)
        new_due_date = _parse_iso_date(due_date, "rok vrnitve")
    except ValueError as exc:
        return RedirectResponse(
            f"/loans?notice={quote_plus(str(exc))}#loan-{loan_id}", status_code=303
        )
    if new_due_date and new_due_date < new_loan_date:
        return RedirectResponse(
            f"/loans?notice={quote_plus('Rok vrnitve ne more biti pred datumom izposoje.')}#loan-{loan_id}",
            status_code=303,
        )
    loan.loan_date = new_loan_date
    loan.due_date = new_due_date
    db.commit()
    return RedirectResponse(
        f"/loans?notice={quote_plus('Datumi izposoje so bili shranjeni.')}#loan-{loan_id}",
        status_code=303,
    )
