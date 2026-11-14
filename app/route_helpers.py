from datetime import date
from urllib.parse import quote_plus
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.config import APP_TITLE
from app.models import Genre, Collection, Room, Cabinet, Shelf
from app.templating import templates
from app.runtime_context import template_context


def render(request, name: str, **context):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"request": request, "title": APP_TITLE, **template_context(request), **context},
    )


def date_value(value: str):
    return date.fromisoformat(value) if value and value.strip() else None


def redirect_notice(path: str, message: str):
    return __import__("fastapi.responses", fromlist=["RedirectResponse"]).RedirectResponse(
        f"{path}?notice={quote_plus(message)}", status_code=303
    )


def location_lists(db: Session, location_id: int):
    return {
        "rooms": db.scalars(select(Room).where(Room.location_id == location_id).order_by(Room.name)).all(),
        "cabinets": db.scalars(
            select(Cabinet).join(Room).where(Room.location_id == location_id)
            .options(selectinload(Cabinet.room)).order_by(Cabinet.name)
        ).all(),
        "shelves": db.scalars(
            select(Shelf).join(Cabinet).join(Room).where(Room.location_id == location_id)
            .options(selectinload(Shelf.cabinet).selectinload(Cabinet.room)).order_by(Shelf.name)
        ).all(),
    }


def book_form_context(db: Session, book=None, location_id: int | None = None):
    selected_location_id = book.location_id if book else location_id
    context = {
        "book": book,
        "genres": db.scalars(select(Genre).order_by(Genre.name)).all(),
        "collections": db.scalars(select(Collection).order_by(Collection.name)).all(),
    }
    if selected_location_id:
        context.update(location_lists(db, selected_location_id))
    else:
        context.update({"rooms": [], "cabinets": [], "shelves": []})
    return context
