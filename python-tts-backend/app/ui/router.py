from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["ui"])

UI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
static_files = StaticFiles(directory=str(STATIC_DIR))


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def application_ui(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "app.html", {"request": request})
