from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.access import require_admin
from app.database import get_db
from app.models import Location, User, UserLocation, FamilyMember
from app.security import hash_password
from app.templating import render_page

router = APIRouter()


@router.get("/admin")
def admin_home(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    locations = db.scalars(select(Location).order_by(Location.name)).all()
    users = db.scalars(select(User).options(selectinload(User.locations).selectinload(UserLocation.location),
                                           selectinload(User.family_member)).order_by(User.username)).all()
    return render_page(request, "admin.html", locations=locations, users=users)


@router.post("/admin/locations/save")
def location_save(request: Request, name: str = Form(...), address: str = Form(""), db: Session = Depends(get_db)):
    require_admin(request)
    name = name.strip()
    if not name:
        raise HTTPException(400, "Ime lokacije je obvezno.")
    if db.scalar(select(Location.id).where(Location.name == name)):
        return RedirectResponse("/admin?notice=Lokacija+že+obstaja", status_code=303)
    db.add(Location(name=name, address=address.strip() or None))
    db.commit()
    return RedirectResponse("/admin?notice=Lokacija+je+bila+dodana", status_code=303)


@router.post("/admin/locations/{location_id}/save")
def location_update(location_id: int, request: Request, name: str = Form(...), address: str = Form(""),
                    active: str = Form("1"), db: Session = Depends(get_db)):
    require_admin(request)
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(404)
    name = name.strip()
    if not name:
        return RedirectResponse("/admin?notice=Ime+lokacije+ne+sme+biti+prazno", status_code=303)
    duplicate = db.scalar(select(Location.id).where(Location.name == name, Location.id != location_id))
    if duplicate:
        return RedirectResponse("/admin?notice=Lokacija+že+obstaja", status_code=303)
    location.name = name
    location.address = address.strip() or None
    location.active = active == "1"
    db.commit()
    return RedirectResponse("/admin?notice=Lokacija+je+bila+posodobljena", status_code=303)


@router.post("/admin/users/save")
def user_save(
    request: Request, username: str = Form(...), display_name: str = Form(...), password: str = Form(...),
    role: str = Form("USER"), location_ids: list[int] = Form([]), db: Session = Depends(get_db),
):
    require_admin(request)
    username = username.strip().lower()
    display_name = display_name.strip()
    role = role.upper()
    if role not in ("ADMIN", "USER"):
        raise HTTPException(400, "Neveljavna vloga.")
    if not username or not display_name or db.scalar(select(User.id).where(User.username == username)):
        return RedirectResponse("/admin?notice=Uporabniško+ime+že+obstaja+ali+so+podatki+prazni", status_code=303)
    if role == "USER" and not location_ids:
        return RedirectResponse("/admin?notice=Običajnemu+uporabniku+dodeli+najmanj+eno+lokacijo", status_code=303)
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return RedirectResponse(f"/admin?notice={str(exc).replace(' ', '+')}", status_code=303)
    user = User(username=username, display_name=display_name, password_hash=password_hash, role=role)
    db.add(user)
    db.flush()
    valid_locations = db.scalars(
        select(Location).where(Location.id.in_(location_ids), Location.active.is_(True)).order_by(Location.name)
    ).all() if location_ids else []
    if role == "USER" and not valid_locations:
        return RedirectResponse("/admin?notice=Izbrane+lokacije+niso+veljavne", status_code=303)
    for location in valid_locations:
        db.add(UserLocation(user_id=user.id, location_id=location.id))
    if role == "USER":
        primary_location = valid_locations[0]
        db.add(FamilyMember(name=display_name, location_id=primary_location.id, user_id=user.id))
    db.commit()
    return RedirectResponse("/admin?notice=Uporabnik+je+bil+ustvarjen", status_code=303)


@router.post("/admin/users/{user_id}/locations")
def user_locations_update(user_id: int, request: Request, location_ids: list[int] = Form([]), db: Session = Depends(get_db)):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.role == "ADMIN":
        return RedirectResponse("/admin?notice=Administratorju+ni+treba+dodeljevati+lokacij", status_code=303)
    valid_locations = db.scalars(
        select(Location).where(Location.id.in_(location_ids), Location.active.is_(True)).order_by(Location.name)
    ).all() if location_ids else []
    if not valid_locations:
        return RedirectResponse("/admin?notice=Uporabnik+mora+imeti+najmanj+eno+aktivno+lokacijo", status_code=303)
    db.query(UserLocation).filter(UserLocation.user_id == user_id).delete(synchronize_session=False)
    for location in valid_locations:
        db.add(UserLocation(user_id=user_id, location_id=location.id))
    member = user.family_member
    if member and member.location_id not in {location.id for location in valid_locations}:
        member.location_id = valid_locations[0].id
    db.commit()
    return RedirectResponse("/admin?notice=Dostopi+so+bili+posodobljeni", status_code=303)


@router.post("/admin/users/{user_id}/toggle")
def user_toggle(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.id == request.state.user.id:
        return RedirectResponse("/admin?notice=Lastnega+računa+ne+moreš+deaktivirati", status_code=303)
    user.active = not user.active
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/users/{user_id}/password")
def user_password(user_id: int, request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    try:
        user.password_hash = hash_password(password)
    except ValueError as exc:
        return RedirectResponse(f"/admin?notice={str(exc).replace(' ', '+')}", status_code=303)
    db.commit()
    return RedirectResponse("/admin?notice=Geslo+je+bilo+spremenjeno", status_code=303)
