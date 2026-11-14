from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Book, Borrower, Loan
from app.route_helpers import date_value, redirect_notice
from app.access import require_location

router = APIRouter()

@router.post("/books/{book_id}/loan")
def loan_book(book_id: int, request: Request, borrower_id: int = Form(...), due_date: str = Form(""), db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    borrower = db.get(Borrower, borrower_id)
    if not book or not borrower:
        return redirect_notice(f"/books/{book_id}", "Izberi veljavnega izposojevalca.")
    require_location(request, book.location_id)
    if borrower.location_id != book.location_id:
        return redirect_notice(f"/books/{book_id}", "Izposojevalec mora biti v isti lokaciji kot knjiga.")
    active = db.scalar(select(Loan).where(Loan.book_id == book_id, Loan.returned_date.is_(None)).limit(1))
    if active:
        return redirect_notice(f"/books/{book_id}", "Ta izvod je že posojen.")
    # Keep the loan date and its standard 30-day deadline tied to one date value.
    loan_day = date.today()
    due = date_value(due_date) or (loan_day + timedelta(days=30))
    if due < loan_day:
        return redirect_notice(f"/books/{book_id}", "Rok vrnitve ne more biti pred datumom izposoje.")
    db.add(Loan(book_id=book_id, borrower_id=borrower_id, loan_date=loan_day, due_date=due))
    db.commit()
    return RedirectResponse(f"/books/{book_id}", status_code=303)

@router.post("/loans/{loan_id}/return")
def return_book(loan_id: int, request: Request, db: Session = Depends(get_db)):
    loan = db.get(Loan, loan_id)
    if loan and not loan.returned_date:
        require_location(request, loan.book.location_id)
        book_id = loan.book_id
        loan.returned_date = date.today()
        db.commit()
        return RedirectResponse(f"/books/{book_id}", status_code=303)
    return RedirectResponse("/books", status_code=303)

