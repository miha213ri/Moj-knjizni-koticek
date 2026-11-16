"""Administracija sistema: uporabniki, vloge, lokacije, nastavitve in revizijska sled."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.access import require_admin
from app.audit import log_audit
from app.config import APP_TITLE, DEFAULT_LOAN_DAYS, REGISTRATION_ENABLED
from app.database import get_db
from app.mailer import (
    get_smtp_config,
    is_smtp_configured,
    send_credentials_email,
    test_smtp_connection,
)
from app.models import (
    AppSetting, AuditLog, Book, FamilyMember, Loan, Location, User, UserLocation
)
from app.security import hash_password, validate_password_strength
from app.templating import render_page

router = APIRouter()


@router.get("/admin")
def admin_home(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    locations = db.scalars(select(Location).order_by(Location.name)).all()
    users = db.scalars(
        select(User)
        .options(
            selectinload(User.locations).selectinload(UserLocation.location),
            selectinload(User.family_member),
        )
        .order_by(User.username)
    ).all()

    # Statistike
    stats = {
        "books": db.scalar(select(func.count(Book.id))) or 0,
        "loans": db.scalar(select(func.count(Loan.id)).where(Loan.returned_date.is_(None))) or 0,
        "users": len(users),
        "locations": len(locations),
    }

    # Zadnjih 50 revizijskih zapisov
    audit_logs = db.scalars(
        select(AuditLog)
        .options(selectinload(AuditLog.user), selectinload(AuditLog.location))
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    ).all()

    # Sistemske nastavitve iz baze ali privzete
    s_title = db.get(AppSetting, "app_title")
    s_reg = db.get(AppSetting, "registration_enabled")
    s_loan = db.get(AppSetting, "default_loan_days")

    settings = {
        "app_title": s_title.value if s_title else APP_TITLE,
        "registration_enabled": s_reg.value if s_reg else ("1" if REGISTRATION_ENABLED else "0"),
        "default_loan_days": s_loan.value if s_loan else str(DEFAULT_LOAN_DAYS),
    }

    smtp_cfg = get_smtp_config(db)
    smtp_active = is_smtp_configured(db)

    return render_page(
        request, "admin.html",
        locations=locations,
        users=users,
        stats=stats,
        audit_logs=audit_logs,
        settings=settings,
        smtp=smtp_cfg,
        smtp_cfg=smtp_cfg,
        smtp_active=smtp_active,
        notice=request.query_params.get("notice", ""),
        error=request.query_params.get("error", ""),
    )


# -----------------------------------------------------------------------------
# Upravljanje lokacij
# -----------------------------------------------------------------------------

@router.post("/admin/locations/save")
def location_save(request: Request, name: str = Form(...), address: str = Form(""), db: Session = Depends(get_db)):
    require_admin(request)
    name = name.strip()
    if not name:
        return RedirectResponse("/admin?error=Ime+lokacije+je+obvezno", status_code=303)
    if db.scalar(select(Location.id).where(Location.name == name)):
        return RedirectResponse("/admin?error=Lokacija+s+tem+imenom+že+obstaja", status_code=303)

    loc = Location(name=name, address=address.strip() or None)
    db.add(loc)
    db.flush()
    log_audit(db, "LOCATION_CREATE", user_id=request.state.user.id, location_id=loc.id, details=f"Ustvarjena lokacija {name}")
    db.commit()
    return RedirectResponse("/admin?notice=Lokacija+je+bila+uspešno+dodana", status_code=303)


@router.post("/admin/locations/{location_id}/save")
def location_update(
    location_id: int, request: Request,
    name: str = Form(...), address: str = Form(""), active: str = Form("1"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(404)
    name = name.strip()
    if not name:
        return RedirectResponse("/admin?error=Ime+lokacije+ne+sme+biti+prazno", status_code=303)
    duplicate = db.scalar(select(Location.id).where(Location.name == name, Location.id != location_id))
    if duplicate:
        return RedirectResponse("/admin?error=Druga+lokacija+s+tem+imenom+že+obstaja", status_code=303)

    location.name = name
    location.address = address.strip() or None
    location.active = (active == "1")
    log_audit(db, "LOCATION_UPDATE", user_id=request.state.user.id, location_id=location.id, details=f"Posodobitev lokacije {name} (aktivna={location.active})")
    db.commit()
    return RedirectResponse("/admin?notice=Lokacija+je+bila+posodobljena", status_code=303)


# -----------------------------------------------------------------------------
# Upravljanje uporabnikov
# -----------------------------------------------------------------------------

@router.post("/admin/users/save")
def user_save(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    role: str = Form("USER"),
    location_ids: list[int] = Form([]),
    send_credentials: str = Form("0"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    username = username.strip().lower()
    display_name = display_name.strip()
    email = email.strip().lower() or None
    role = role.upper()

    if role not in ("ADMIN", "EDITOR", "USER", "GUEST"):
        return RedirectResponse("/admin?error=Neveljavna+uporabniška+vloga", status_code=303)
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", username):
        return RedirectResponse("/admin?error=Uporabniško+ime+mora+imeti+3-50+znakov", status_code=303)
    if not display_name:
        return RedirectResponse("/admin?error=Prikazno+ime+je+obvezno", status_code=303)
    if db.scalar(select(User.id).where(func.lower(User.username) == username)):
        return RedirectResponse("/admin?error=Uporabniško+ime+že+obstaja", status_code=303)
    if email and db.scalar(select(User.id).where(func.lower(User.email) == email)):
        return RedirectResponse("/admin?error=E-poštni+naslov+že+uporablja+drug+račun", status_code=303)

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return RedirectResponse(f"/admin?error={str(exc).replace(' ', '+')}", status_code=303)

    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=password_hash,
        role=role,
        active=True,
    )
    db.add(user)
    db.flush()

    valid_locations = db.scalars(
        select(Location).where(Location.id.in_(location_ids), Location.active.is_(True)).order_by(Location.name)
    ).all() if location_ids else []

    if role != "ADMIN" and not valid_locations:
        # Če niso izbrane lokacije, dodelimo privzeto
        first_loc = db.scalar(select(Location).where(Location.active.is_(True)).order_by(Location.id).limit(1))
        if first_loc:
            valid_locations = [first_loc]

    for loc in valid_locations:
        db.add(UserLocation(user_id=user.id, location_id=loc.id))

    if valid_locations:
        db.add(FamilyMember(name=display_name, location_id=valid_locations[0].id, user_id=user.id, active=True))

    log_audit(db, "USER_CREATE", user_id=request.state.user.id, details=f"Ustvarjen uporabnik {username} z vlogo {role}")
    db.commit()

    if send_credentials == "1" and user.email:
        login_url = str(request.base_url).rstrip("/") + "/login"
        sent = send_credentials_email(user.email, user.display_name, user.username, password.strip(), login_url, db=db)
        if sent:
            log_audit(db, "CREDENTIALS_EMAIL_SENT", user_id=request.state.user.id, details=f"Prijavni podatki poslani na {user.email}")
            db.commit()

    return RedirectResponse("/admin?notice=Uporabnik+je+bil+uspešno+ustvarjen", status_code=303)


@router.post("/admin/users/{user_id}/locations")
def user_locations_update(
    user_id: int, request: Request, location_ids: list[int] = Form([]), db: Session = Depends(get_db)
):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.role == "ADMIN":
        return RedirectResponse("/admin?notice=Administrator+ima+samodejno+dostop+do+vseh+lokacij", status_code=303)

    valid_locations = db.scalars(
        select(Location).where(Location.id.in_(location_ids), Location.active.is_(True)).order_by(Location.name)
    ).all() if location_ids else []

    db.query(UserLocation).filter(UserLocation.user_id == user_id).delete(synchronize_session=False)
    for loc in valid_locations:
        db.add(UserLocation(user_id=user_id, location_id=loc.id))

    member = user.family_member
    if member and valid_locations and member.location_id not in {l.id for l in valid_locations}:
        member.location_id = valid_locations[0].id

    log_audit(db, "USER_LOCATIONS_UPDATE", user_id=request.state.user.id, details=f"Spremenjene lokacije za uporabnika {user.username}")
    db.commit()
    return RedirectResponse("/admin?notice=Dostopi+do+lokacij+so+bili+posodobljeni", status_code=303)


@router.post("/admin/users/{user_id}/role")
def user_role_update(
    user_id: int, request: Request, role: str = Form(...), db: Session = Depends(get_db)
):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.id == request.state.user.id:
        return RedirectResponse("/admin?error=Lastne+vloge+ne+morete+spremeniti", status_code=303)

    role = role.upper()
    if role not in ("ADMIN", "EDITOR", "USER", "GUEST"):
        return RedirectResponse("/admin?error=Neveljavna+vloga", status_code=303)

    old_role = user.role
    user.role = role
    user.session_version = (user.session_version or 1) + 1  # Osveži sejo uporabnika
    log_audit(db, "USER_ROLE_CHANGE", user_id=request.state.user.id, details=f"Vloga uporabnika {user.username} spremenjena: {old_role} -> {role}")
    db.commit()
    return RedirectResponse("/admin?notice=Vloga+uporabnika+je+bila+posodobljena", status_code=303)


@router.post("/admin/users/{user_id}/toggle")
def user_toggle(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.id == request.state.user.id:
        return RedirectResponse("/admin?error=Lastnega+računa+ne+morete+deaktivirati", status_code=303)

    user.active = not user.active
    if not user.active:
        user.session_version = (user.session_version or 1) + 1  # Takoj prekine prijavo
    status_str = "aktiviran" if user.active else "deaktiviran"
    log_audit(db, "USER_TOGGLE_ACTIVE", user_id=request.state.user.id, details=f"Uporabnik {user.username} je bil {status_str}")
    db.commit()
    return RedirectResponse(f"/admin?notice=Uporabnik+je+bil+{status_str}", status_code=303)


@router.post("/admin/users/{user_id}/unlock")
def user_unlock(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    user.failed_logins = 0
    user.locked_until = None
    log_audit(db, "USER_UNLOCK", user_id=request.state.user.id, details=f"Uporabnik {user.username} je bil ročno odklenjen.")
    db.commit()
    return RedirectResponse("/admin?notice=Račun+je+bil+uspešno+odklenjen", status_code=303)


@router.post("/admin/users/{user_id}/password")
def user_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    send_credentials: str = Form("0"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    try:
        user.password_hash = hash_password(password)
        user.session_version = (user.session_version or 1) + 1
        user.failed_logins = 0
        user.locked_until = None
    except ValueError as exc:
        return RedirectResponse(f"/admin?error={str(exc).replace(' ', '+')}", status_code=303)

    log_audit(db, "ADMIN_PASSWORD_RESET", user_id=request.state.user.id, details=f"Skrbnik je ponastavil geslo za uporabnika {user.username}")
    db.commit()

    if send_credentials == "1" and user.email:
        login_url = str(request.base_url).rstrip("/") + "/login"
        sent = send_credentials_email(user.email, user.display_name, user.username, password.strip(), login_url, db=db)
        if sent:
            log_audit(db, "CREDENTIALS_EMAIL_SENT", user_id=request.state.user.id, details=f"Novo geslo poslano na {user.email}")
            db.commit()

    return RedirectResponse("/admin?notice=Geslo+uporabnika+je+bilo+uspešno+ponastavljeno", status_code=303)


# -----------------------------------------------------------------------------
# Sistemske nastavitve in konfiguracija SMTP
# -----------------------------------------------------------------------------

@router.post("/admin/settings/save")
def settings_save(
    request: Request,
    app_title: str = Form(...),
    registration_enabled: str = Form("0"),
    default_loan_days: str = Form("30"),
    db: Session = Depends(get_db),
):
    require_admin(request)

    def _set(key: str, val: str, desc: str = ""):
        item = db.get(AppSetting, key)
        if not item:
            item = AppSetting(key=key, value=val, description=desc)
            db.add(item)
        else:
            item.value = val
            item.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    _set("app_title", app_title.strip() or APP_TITLE, "Naziv aplikacije")
    _set("registration_enabled", "1" if registration_enabled == "1" else "0", "Omogočena javna registracija")
    _set("default_loan_days", str(int(default_loan_days) if default_loan_days.isdigit() else 30), "Privzeti rok izposoje v dneh")

    log_audit(db, "SETTINGS_UPDATE", user_id=request.state.user.id, details="Posodobitev sistemskih nastavitev knjižnice.")
    db.commit()
    return RedirectResponse("/admin?notice=Sistemske+nastavitve+so+bile+uspešno+shranjene", status_code=303)


@router.post("/admin/smtp/save")
def smtp_save(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_from: str = Form(""),
    smtp_from_name: str = Form(""),
    smtp_security: str = Form("tls"),
    db: Session = Depends(get_db),
):
    require_admin(request)

    def _set(key: str, val: str, desc: str = ""):
        item = db.get(AppSetting, key)
        if not item:
            item = AppSetting(key=key, value=val, description=desc)
            db.add(item)
        else:
            item.value = val
            item.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    _set("smtp_host", smtp_host.strip(), "SMTP strežnik")
    _set("smtp_port", smtp_port.strip() or "587", "SMTP vrata")
    _set("smtp_user", smtp_user.strip(), "SMTP uporabnik")
    if smtp_password.strip():
        _set("smtp_password", smtp_password.strip(), "SMTP geslo")
    _set("smtp_from", smtp_from.strip(), "SMTP pošiljatelj e-pošta")
    _set("smtp_from_name", smtp_from_name.strip() or APP_TITLE, "SMTP pošiljatelj naziv")
    _set("smtp_security", smtp_security.strip().lower(), "SMTP varnost (tls, ssl, none)")

    log_audit(db, "SETTINGS_SMTP_UPDATE", user_id=request.state.user.id, details="Posodobitev SMTP nastavitev.")
    db.commit()
    return RedirectResponse("/admin?notice=SMTP+nastavitve+so+bile+uspešno+shranjene", status_code=303)


@router.post("/admin/smtp/test")
def smtp_test(
    request: Request,
    test_email: str = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    cfg = get_smtp_config(db)
    success, message = test_smtp_connection(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        security=cfg["security"],
        from_email=cfg["from_email"],
        from_name=cfg["from_name"],
        test_recipient=test_email.strip(),
    )
    if success:
        log_audit(db, "TEST_SMTP_SUCCESS", user_id=request.state.user.id, details=f"Uspešen test SMTP na {test_email}")
        return RedirectResponse(f"/admin?notice={quote(message)}", status_code=303)
    else:
        log_audit(db, "TEST_SMTP_FAILURE", user_id=request.state.user.id, details=f"Neuspešen test SMTP: {message}")
        return RedirectResponse(f"/admin?error={quote(message)}", status_code=303)

