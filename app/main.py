from __future__ import annotations

import time
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_ENV, APP_SECRET_KEY, APP_TITLE, BASE_DIR, SESSION_HTTPS_ONLY
from app.database import Base, SessionLocal, engine
from app.migrations import auto_migrate_schema
from app.models import FamilyMember, Location, User, UserLocation
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.backup import router as backup_router
from app.routes.books import router as books_router
from app.routes.borrowers import router as borrowers_router
from app.routes.library_api import router as library_api_router
from app.routes.loan_actions import router as loan_actions_router
from app.routes.loans import router as loans_router
from app.routes.readings_wishes import router as readings_router
from app.routes.settings import router as settings_router

# Inicializacija baze in samodejna migracija sheme
Base.metadata.create_all(bind=engine)
auto_migrate_schema(engine)

app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

for router in (
    auth_router, admin_router, books_router, borrowers_router,
    loan_actions_router, readings_router, settings_router,
    library_api_router, loans_router, backup_router,
):
    app.include_router(router)

# Preprost spominski rate-limiter za prijavo (zaščita pred brute-force)
_login_attempts: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    path = request.url.path

    # Zaščita pred CSRF prek Origin/Referer preverjanja pri POST/PUT/DELETE
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or referer
        if source:
            source_host = (urlparse(source).hostname or "").lower()
            request_host = (request.headers.get("host", "").split(":", 1)[0]).lower()
            if source_host and request_host and source_host != request_host:
                return JSONResponse({"detail": "Zahteva iz drugega spletnega vira je bila zavrnjena."}, status_code=403)

    # Omejevanje frekvence prijav (Rate limiting)
    if path == "/login" and request.method == "POST":
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        # Odstrani poskuse, starejše od 60 sekund
        _login_attempts[client_ip] = [t for t in _login_attempts[client_ip] if now - t < 60]
        if len(_login_attempts[client_ip]) >= 20:
            return JSONResponse({"detail": "Preveč poskusov prijave. Počakajte minuto."}, status_code=429)
        _login_attempts[client_ip].append(now)

    public_paths = {
        "/login", "/logout", "/register", "/forgot-password",
        "/reset-password", "/health", "/robots.txt",
    }
    is_public = path in public_paths or path.startswith("/static/")

    if is_public:
        response = await call_next(request)
        _add_security_headers(response)
        return response

    user_id = request.session.get("user_id")
    if not user_id:
        if request.method in ("GET", "HEAD"):
            next_url = request.url.path
            if request.url.query:
                next_url += "?" + request.url.query
            return RedirectResponse(f"/login?next={next_url}", status_code=303)
        return JSONResponse({"detail": "Prijava je potekla. Prosimo, ponovno se prijavite."}, status_code=401)

    with SessionLocal() as auth_db:
        user = auth_db.get(User, int(user_id))
        if not user or not user.active:
            request.session.clear()
            return RedirectResponse("/login?notice=Račun+je+neaktiven+ali+ne+obstaja.", status_code=303)

        # Preverjanje preklica sej (Session Revocation)
        cookie_version = request.session.get("session_version", 1)
        if user.session_version and cookie_version != user.session_version:
            request.session.clear()
            return RedirectResponse("/login?notice=Vaša+seja+je+potekla.+Prijavite+se+znova.", status_code=303)

        if user.role == "ADMIN":
            locations = auth_db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.name)).all()
        else:
            locations = auth_db.scalars(
                select(Location).join(UserLocation, UserLocation.location_id == Location.id)
                .where(UserLocation.user_id == user.id, Location.active.is_(True)).order_by(Location.name)
            ).all()

        member_id = auth_db.scalar(select(FamilyMember.id).where(FamilyMember.user_id == user.id).limit(1))
        state_user = type("CurrentUser", (), {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "email": user.email,
        })()
        location_rows = [{"id": loc.id, "name": loc.name} for loc in locations]
        allowed_ids = {loc.id for loc in locations}
        active_id = request.session.get("active_location_id")
        if active_id not in allowed_ids:
            active_id = locations[0].id if locations else None
            if active_id:
                request.session["active_location_id"] = active_id

    if not allowed_ids and user.role != "ADMIN":
        return JSONResponse({"detail": "Uporabniškemu računu ni dodeljena nobena aktivna lokacija."}, status_code=403)

    request.state.user = state_user
    request.state.locations = location_rows
    request.state.allowed_location_ids = allowed_ids
    request.state.current_location_id = active_id
    request.state.current_location = next((loc for loc in location_rows if loc["id"] == active_id), None)
    request.state.family_member_id = member_id

    response = await call_next(request)
    _add_security_headers(response)
    return response


def _add_security_headers(response):
    """Dodajanje standardnih varnostnih HTTP glav za zaščito pred XSS, clickjackingom itd."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    """Zasebna knjižnica – prepoved indeksiranja spletnim pajkom."""
    return "User-agent: *\nDisallow: /\n"


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
