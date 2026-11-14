from fastapi.templating import Jinja2Templates
from app.config import BASE_DIR, APP_TITLE
from app.runtime_context import template_context

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def render_page(request, name: str, **context):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"request": request, "title": APP_TITLE, **template_context(request), **context},
    )
