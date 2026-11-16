"""Preverjanje uporabniških pravic in ločevanje dostopa po vlogah in lokacijah."""
from __future__ import annotations

from fastapi import HTTPException, Request


def get_current_user(request: Request):
    return getattr(request.state, "user", None)


def is_admin(request: Request) -> bool:
    user = get_current_user(request)
    return bool(user and getattr(user, "role", "") == "ADMIN")


def is_editor(request: Request) -> bool:
    user = get_current_user(request)
    return bool(user and getattr(user, "role", "") in ("ADMIN", "EDITOR"))


def is_guest(request: Request) -> bool:
    user = get_current_user(request)
    return bool(user and getattr(user, "role", "") == "GUEST")


def can_manage_books(request: Request, location_id: int | None = None) -> bool:
    if is_admin(request):
        return True
    if not is_editor(request):
        return False
    if location_id is None:
        return True
    return int(location_id) in allowed_location_ids(request)


def current_location_id(request: Request) -> int:
    value = getattr(request.state, "current_location_id", None)
    if not value:
        raise HTTPException(403, "Uporabniku ni dodeljena aktivna knjižnica.")
    return int(value)


def allowed_location_ids(request: Request) -> set[int]:
    return set(getattr(request.state, "allowed_location_ids", set()))


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(403, "Za to dejanje so potrebne skrbniške pravice (ADMIN).")


def require_editor(request: Request) -> None:
    if not is_editor(request):
        raise HTTPException(403, "Za to dejanje so potrebne uredniške pravice (EDITOR ali ADMIN).")


def require_not_guest(request: Request) -> None:
    if is_guest(request):
        raise HTTPException(403, "Gostom je omogočen le vpogled. Za spreminjanje podatkov se obrnite na skrbnika.")


def require_location(request: Request, location_id: int | None) -> None:
    if is_admin(request):
        return
    require_not_guest(request)
    if location_id is None or int(location_id) not in allowed_location_ids(request):
        raise HTTPException(403, "Za to lokacijo nimate pravic za spreminjanje podatkov.")


def member_filter_id(request: Request) -> int | None:
    """Običajni uporabniki vidijo le svoj družinski profil; administratorji vidijo vse."""
    if is_admin(request):
        return None
    member_id = getattr(request.state, "family_member_id", None)
    if not member_id:
        raise HTTPException(403, "Uporabniški račun nima povezanega profila. Obrnite se na skrbnika.")
    return int(member_id)
