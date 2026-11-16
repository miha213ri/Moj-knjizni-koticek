def template_context(request):
    user = getattr(request.state, "user", None)
    role = getattr(user, "role", "") if user else ""
    return {
        "user": user,
        "is_admin": bool(role == "ADMIN"),
        "is_editor": bool(role in ("ADMIN", "EDITOR")),
        "is_guest": bool(role == "GUEST"),
        "locations": getattr(request.state, "locations", []),
        "current_location_id": getattr(request.state, "current_location_id", None),
        "current_location": getattr(request.state, "current_location", None),
        "can_manage_location_ids": getattr(request.state, "allowed_location_ids", set()),
    }
