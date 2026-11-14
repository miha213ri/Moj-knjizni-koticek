from fastapi import HTTPException, Request


def is_admin(request: Request) -> bool:
    return bool(getattr(getattr(request.state, "user", None), "role", "") == "ADMIN")


def current_location_id(request: Request) -> int:
    value = getattr(request.state, "current_location_id", None)
    if not value:
        raise HTTPException(403, "Uporabniku ni dodeljena aktivna knjižnica.")
    return int(value)


def allowed_location_ids(request: Request) -> set[int]:
    return set(getattr(request.state, "allowed_location_ids", set()))


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(403, "Za to dejanje so potrebne administratorske pravice.")


def require_location(request: Request, location_id: int | None) -> None:
    if is_admin(request):
        return
    if location_id is None or int(location_id) not in allowed_location_ids(request):
        raise HTTPException(403, "Za to lokacijo nimaš pravic za spreminjanje podatkov.")


def member_filter_id(request: Request) -> int | None:
    """Normal users may use only their linked family profile; admins see all."""
    if is_admin(request):
        return None
    member_id = getattr(request.state, "family_member_id", None)
    if not member_id:
        raise HTTPException(403, "Tvoj uporabniški račun še nima povezanega družinskega profila. Obrni se na administratorja.")
    return int(member_id)
