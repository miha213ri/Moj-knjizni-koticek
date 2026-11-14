def template_context(request):
    user = getattr(request.state, "user", None)
    return {
        "user": user,
        "is_admin": bool(user and user.role == "ADMIN"),
        "locations": getattr(request.state, "locations", []),
        "current_location_id": getattr(request.state, "current_location_id", None),
        "current_location": getattr(request.state, "current_location", None),
        "can_manage_location_ids": getattr(request.state, "allowed_location_ids", set()),
    }
