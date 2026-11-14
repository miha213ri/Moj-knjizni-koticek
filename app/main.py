from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, APP_TITLE, APP_ENV, APP_SECRET_KEY, SESSION_HTTPS_ONLY
from app.database import Base, engine, SessionLocal
from app.models import Location, User, UserLocation, FamilyMember
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.books import router as books_router
from app.routes.borrowers import router as borrowers_router
from app.routes.loan_actions import router as loan_actions_router
from app.routes.readings_wishes import router as readings_router
from app.routes.settings import router as settings_router
from app.routes.library_api import router as library_api_router
from app.routes.loans import router as loans_router
from app.routes.backup import router as backup_router


# Schema creation is idempotent. The first administrator is created separately
# with scripts/create_admin.py; no default password is ever shipped.
Base.metadata.create_all(bind=engine)
if engine.dialect.name == "sqlite":
    from app.migrations import migrate_reading_records
    migrate_reading_records()

app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
for router in (auth_router, admin_router, books_router, borrowers_router, loan_actions_router,
               readings_router, settings_router, library_api_router, loans_router, backup_router):
    app.include_router(router)


@app.middleware("http")
async def login_and_origin_guard(request: Request, call_next):
    path = request.url.path
    public = path == "/login" or path == "/health" or path.startswith("/static/")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or referer
        if source:
            source_host = (urlparse(source).hostname or "").lower()
            request_host = (request.headers.get("host", "").split(":", 1)[0]).lower()
            if source_host and request_host and source_host != request_host:
                return JSONResponse({"detail": "Zahteva iz druge spletne strani je zavrnjena."}, status_code=403)
    if public:
        return await call_next(request)

    user_id = request.session.get("user_id")
    if not user_id:
        if request.method in ("GET", "HEAD"):
            next_url = request.url.path
            if request.url.query:
                next_url += "?" + request.url.query
            return RedirectResponse(f"/login?next={next_url}", status_code=303)
        return JSONResponse({"detail": "Prijava je potekla. Ponovno se prijavi."}, status_code=401)

    with SessionLocal() as auth_db:
        user = auth_db.get(User, int(user_id))
        if not user or not user.active:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        if user.role == "ADMIN":
            locations = auth_db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.name)).all()
        else:
            locations = auth_db.scalars(
                select(Location).join(UserLocation, UserLocation.location_id == Location.id)
                .where(UserLocation.user_id == user.id, Location.active.is_(True)).order_by(Location.name)
            ).all()
        member_id = auth_db.scalar(select(FamilyMember.id).where(FamilyMember.user_id == user.id).limit(1))
        state_user = type("CurrentUser", (), {
            "id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role
        })()
        location_rows = [{"id": loc.id, "name": loc.name} for loc in locations]
        allowed_ids = {loc.id for loc in locations}
        active_id = request.session.get("active_location_id")
        if active_id not in allowed_ids:
            active_id = locations[0].id if locations else None
            if active_id:
                request.session["active_location_id"] = active_id

    if not allowed_ids:
        return JSONResponse({"detail": "Uporabniškemu računu ni dodeljena nobena aktivna lokacija."}, status_code=403)
    request.state.user = state_user
    request.state.locations = location_rows
    request.state.allowed_location_ids = allowed_ids
    request.state.current_location_id = active_id
    request.state.current_location = next((loc for loc in location_rows if loc["id"] == active_id), None)
    request.state.family_member_id = member_id
    return await call_next(request)


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return {"status": "ok", "database": "connected", "application": APP_TITLE}
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)


if not APP_SECRET_KEY:
    if APP_ENV == "production":
        raise RuntimeError("APP_SECRET_KEY manjka. Nastavi ga v .env pred zagonom aplikacije.")
    APP_SECRET_KEY = "development-only-change-this-secret-before-deploying"

application = SessionMiddleware(
    app,
    secret_key=APP_SECRET_KEY,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY if APP_ENV == "production" else False,
    max_age=60 * 60 * 24 * 14,
)
