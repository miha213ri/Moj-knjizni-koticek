from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Location, UserLocation
from app.security import verify_password
from app.templating import render_page

router = APIRouter()


@router.get("/login")
def login_page(request: Request, next: str = "/books"):
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/books"
    return render_page(request, "login.html", next=safe_next, error="")


@router.post("/login")
def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...),
    next: str = Form("/books"), db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return render_page(request, "login.html", next="/books", error="Uporabniško ime ali geslo ni pravilno.")
    if user.role != "ADMIN" and not db.scalar(select(UserLocation.location_id).where(UserLocation.user_id == user.id).limit(1)):
        return render_page(request, "login.html", next="/books", error="Račun nima dodeljene knjižnice. Obrni se na administratorja.")
    request.session.clear()
    request.session["user_id"] = user.id
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/books"
    return RedirectResponse(safe_next, status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/location/switch")
def switch_location(request: Request, location_id: int = Form(...)):
    allowed = getattr(request.state, "allowed_location_ids", set())
    if location_id not in allowed:
        raise HTTPException(403, "Do izbrane lokacije nimaš dostopa.")
    request.session["active_location_id"] = location_id
    return RedirectResponse(request.headers.get("referer", "/books"), status_code=303)
