"""Prijava, registracija, ponastavitev gesla, profil in upravljanje sej."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.config import REGISTRATION_ENABLED
from app.database import get_db
from app.mailer import send_password_reset_email
from app.models import AppSetting, FamilyMember, Location, PasswordReset, User, UserLocation
from app.security import hash_password, verify_password, validate_password_strength
from app.templating import render_page

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_registration_allowed(db: Session) -> bool:
    setting = db.get(AppSetting, "registration_enabled")
    if setting is not None:
        return setting.value.strip().lower() in ("1", "true", "yes", "da")
    return REGISTRATION_ENABLED


# -----------------------------------------------------------------------------
# Prijava in odjava
# -----------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/books", db: Session = Depends(get_db)):
    if getattr(request.state, "user", None):
        return RedirectResponse("/books", status_code=303)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/books"
    return render_page(
        request, "login.html",
        next=safe_next, error="",
        notice=request.query_params.get("notice", ""),
        registration_enabled=_is_registration_allowed(db),
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/books"),
    db: Session = Depends(get_db),
):
    clean_identifier = username.strip().lower()
    user = db.scalar(
        select(User).where(or_(
            func.lower(User.username) == clean_identifier,
            func.lower(User.email) == clean_identifier,
        )).limit(1)
    )

    if not user:
        log_audit(db, "LOGIN_FAILED", details=f"Neobstoječ uporabnik: {clean_identifier}")
        db.commit()
        return render_page(
            request, "login.html", next="/books",
            error="Uporabniško ime ali geslo ni pravilno.",
            registration_enabled=_is_registration_allowed(db),
        )

    # 1. Preverjanje zaklepa računa (Lockout zaščita pred brute-force)
    now = _utcnow()
    if user.locked_until and user.locked_until > now:
        minutes_left = int((user.locked_until - now).total_seconds() / 60) + 1
        return render_page(
            request, "login.html", next="/books",
            error=f"Račun je začasno zaklenjen zaradi večkratnih napačnih poskusov. Poskusite znova čez {minutes_left} min.",
            registration_enabled=_is_registration_allowed(db),
        )

    # 2. Preverjanje aktivnosti računa
    if not user.active:
        return render_page(
            request, "login.html", next="/books",
            error="Vaš uporabniški račun je deaktiviran. Obrnite se na skrbnika knjižnice.",
            registration_enabled=_is_registration_allowed(db),
        )

    # 3. Preverjanje gesla
    if not verify_password(password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        log_audit(db, "LOGIN_FAILED", user_id=user.id, details=f"Napačno geslo ({user.failed_logins}/5)")
        if user.failed_logins >= 5:
            user.locked_until = now + timedelta(minutes=15)
            log_audit(db, "ACCOUNT_LOCKED", user_id=user.id, details="Račun zaklenjen za 15 minut.")
            db.commit()
            return render_page(
                request, "login.html", next="/books",
                error="Zaradi 5 napačnih poskusov je račun začasno zaklenjen za 15 minut.",
                registration_enabled=_is_registration_allowed(db),
            )
        remaining = 5 - user.failed_logins
        db.commit()
        return render_page(
            request, "login.html", next="/books",
            error=f"Uporabniško ime ali geslo ni pravilno. Preostali poskusi: {remaining}.",
            registration_enabled=_is_registration_allowed(db),
        )

    # 4. Uspešna prijava
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["session_version"] = user.session_version or 1

    log_audit(db, "LOGIN_SUCCESS", user_id=user.id, details=f"Uspešna prijava uporabnika {user.username}")
    db.commit()

    safe_next = next if next.startswith("/") and not next.startswith("//") else "/books"
    return RedirectResponse(safe_next, status_code=303)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if user:
        log_audit(db, "LOGOUT", user_id=user.id, details="Uporabnik se je odjavil.")
        db.commit()
    request.session.clear()
    return RedirectResponse("/login?notice=Uspešno+ste+se+odjavili.", status_code=303)


# -----------------------------------------------------------------------------
# Registracija novih uporabnikov
# -----------------------------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if getattr(request.state, "user", None):
        return RedirectResponse("/books", status_code=303)
    if not _is_registration_allowed(db):
        return render_page(request, "login.html", next="/books", error="Javna registracija je trenutno onemogočena.")
    return render_page(request, "register.html", error="")


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if not _is_registration_allowed(db):
        return render_page(request, "login.html", next="/books", error="Javna registracija je trenutno onemogočena.")

    username = username.strip().lower()
    display_name = display_name.strip()
    email = email.strip().lower() or None

    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", username):
        return render_page(request, "register.html", error="Uporabniško ime mora imeti 3–50 znakov (brez presledkov in posebnih znakov).")
    if not display_name:
        return render_page(request, "register.html", error="Prikazno ime je obvezno.")
    if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return render_page(request, "register.html", error="Vnesite veljaven e-poštni naslov.")
    if password != confirm_password:
        return render_page(request, "register.html", error="Gesli se ne ujemata.")
    if len(password) < 12:
        return render_page(request, "register.html", error="Geslo mora vsebovati najmanj 12 znakov.")

    # Preverjanje enoličnosti
    if db.scalar(select(User.id).where(func.lower(User.username) == username)):
        return render_page(request, "register.html", error="To uporabniško ime je že zasedeno.")
    if email and db.scalar(select(User.id).where(func.lower(User.email) == email)):
        return render_page(request, "register.html", error="Ta e-poštni naslov že uporablja drug račun.")

    # Dodelitev privzete lokacije
    default_loc = db.scalar(select(Location).where(Location.active.is_(True)).order_by(Location.id).limit(1))
    if not default_loc:
        default_loc = Location(name="Glavna knjižnica", active=True)
        db.add(default_loc)
        db.flush()

    pwd_hash = hash_password(password)
    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=pwd_hash,
        role="USER",
        active=True,
    )
    db.add(user)
    db.flush()

    db.add(UserLocation(user_id=user.id, location_id=default_loc.id))
    db.add(FamilyMember(name=display_name, location_id=default_loc.id, user_id=user.id, active=True))

    log_audit(db, "REGISTER", user_id=user.id, location_id=default_loc.id, details=f"Nov uporabnik {username} se je registriral.")
    db.commit()

    return RedirectResponse("/login?notice=Registracija+uspešna!+Zdaj+se+lahko+prijavite.", status_code=303)


# -----------------------------------------------------------------------------
# Pozabljeno geslo in varna ponastavitev
# -----------------------------------------------------------------------------

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return render_page(request, "forgot_password.html", error="", notice="")


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(
    request: Request,
    identifier: str = Form(...),
    db: Session = Depends(get_db),
):
    clean = identifier.strip().lower()
    user = db.scalar(
        select(User).where(or_(
            func.lower(User.username) == clean,
            func.lower(User.email) == clean,
        )).limit(1)
    )

    if user and user.email:
        token = secrets.token_urlsafe(32)
        reset = PasswordReset(
            user_id=user.id,
            token=token,
            expires_at=_utcnow() + timedelta(hours=1),
        )
        db.add(reset)
        db.flush()

        base_url = str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/reset-password?token={token}"
        send_password_reset_email(user.email, user.display_name or user.username, reset_url, db=db)
        log_audit(db, "PASSWORD_RESET_REQUEST", user_id=user.id, details=f"Zahteva za ponastavitev gesla (žeton velja 1h).")
        db.commit()
    elif user and not user.email:
        log_audit(db, "PASSWORD_RESET_NO_EMAIL", user_id=user.id, details="Zahteva za ponastavitev, vendar uporabnik nima nastavljene e-pošte.")
        db.commit()

    return render_page(
        request, "forgot_password.html",
        notice="Če račun z navedenimi podatki obstaja in ima vpisano e-pošto, so bila navodila za ponastavitev poslana.",
        error="",
    )


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str = "", db: Session = Depends(get_db)):
    if not token:
        return RedirectResponse("/forgot-password?error=Manjka+žeton+za+ponastavitev.", status_code=303)
    reset = db.scalar(
        select(PasswordReset).where(
            PasswordReset.token == token,
            PasswordReset.used.is_(False),
            PasswordReset.expires_at > _utcnow(),
        ).limit(1)
    )
    if not reset:
        return render_page(request, "forgot_password.html", error="Povezava za ponastavitev je neveljavna ali pa je že potekla.")
    return render_page(request, "reset_password.html", token=token, error="")


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    reset = db.scalar(
        select(PasswordReset).where(
            PasswordReset.token == token,
            PasswordReset.used.is_(False),
            PasswordReset.expires_at > _utcnow(),
        ).limit(1)
    )
    if not reset:
        return render_page(request, "forgot_password.html", error="Povezava za ponastavitev je neveljavna ali pa je že potekla.")

    if password != confirm_password:
        return render_page(request, "reset_password.html", token=token, error="Gesli se ne ujemata.")
    if len(password) < 12:
        return render_page(request, "reset_password.html", token=token, error="Novo geslo mora vsebovati najmanj 12 znakov.")

    user = reset.user
    user.password_hash = hash_password(password)
    user.session_version = (user.session_version or 1) + 1  # Razveljavi obstoječe seje na vseh napravah
    user.failed_logins = 0
    user.locked_until = None
    reset.used = True

    log_audit(db, "PASSWORD_RESET_SUCCESS", user_id=user.id, details="Geslo uspešno ponastavljeno z žetonom.")
    db.commit()

    return RedirectResponse("/login?notice=Geslo+je+bilo+uspešno+ponastavljeno.+Zdaj+se+lahko+prijavite.", status_code=303)


# -----------------------------------------------------------------------------
# Uporabniški profil in nastavitve računa
# -----------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)
    db_user = db.get(User, user.id)
    return render_page(
        request, "profile.html",
        db_user=db_user,
        notice=request.query_params.get("notice", ""),
        error=request.query_params.get("error", ""),
    )


@router.post("/profile/update")
def profile_update(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401)
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(404)

    display_name = display_name.strip()
    email = email.strip().lower() or None

    if not display_name:
        return RedirectResponse("/profile?error=Prikazno+ime+ne+sme+biti+prazno", status_code=303)
    if email:
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return RedirectResponse("/profile?error=Vnesite+veljaven+e-poštni+naslov", status_code=303)
        dup = db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != db_user.id))
        if dup:
            return RedirectResponse("/profile?error=Ta+e-poštni+naslov+že+uporablja+drug+račun", status_code=303)

    db_user.display_name = display_name
    db_user.email = email
    if db_user.family_member:
        db_user.family_member.name = display_name

    log_audit(db, "PROFILE_UPDATE", user_id=db_user.id, details="Posodobitev osebnih podatkov profila.")
    db.commit()
    return RedirectResponse("/profile?notice=Podatki+profila+so+bili+uspešno+posodobljeni.", status_code=303)


@router.post("/profile/password")
def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401)
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(404)

    if not verify_password(current_password, db_user.password_hash):
        return RedirectResponse("/profile?error=Trenutno+geslo+ni+pravilno", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/profile?error=Novo+geslo+in+potrditev+se+ne+ujamata", status_code=303)
    if len(new_password) < 12:
        return RedirectResponse("/profile?error=Novo+geslo+mora+vsebovati+najmanj+12+znakov", status_code=303)

    db_user.password_hash = hash_password(new_password)
    db_user.session_version = (db_user.session_version or 1) + 1
    db.commit()

    # Posodobimo trenutno sejo, da uporabnik tukaj ostane prijavljen
    request.session["session_version"] = db_user.session_version

    log_audit(db, "PASSWORD_CHANGE", user_id=db_user.id, details="Uporabnik je zamenjal svoje geslo.")
    db.commit()
    return RedirectResponse("/profile?notice=Geslo+je+bilo+uspešno+spremenjeno.+Vse+ostale+naprave+so+odjavljene.", status_code=303)


@router.post("/profile/logout-all")
def profile_logout_all(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401)
    db_user = db.get(User, user.id)
    if db_user:
        db_user.session_version = (db_user.session_version or 1) + 1
        db.commit()
        request.session["session_version"] = db_user.session_version
        log_audit(db, "LOGOUT_ALL_DEVICES", user_id=db_user.id, details="Odjava vseh ostalih sej.")
        db.commit()
    return RedirectResponse("/profile?notice=Vse+ostale+naprave+so+bile+uspešno+odjavljene.", status_code=303)


@router.post("/location/switch")
def switch_location(request: Request, location_id: int = Form(...)):
    allowed = getattr(request.state, "allowed_location_ids", set())
    if location_id not in allowed:
        raise HTTPException(403, "Do izbrane lokacije nimate dostopa.")
    request.session["active_location_id"] = location_id
    return RedirectResponse(request.headers.get("referer", "/books"), status_code=303)
