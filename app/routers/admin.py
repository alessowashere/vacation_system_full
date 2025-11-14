# app/routers/admin.py
# (Archivo nuevo)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime

from app import crud, models, schemas
from app.auth import get_current_admin_user
from app.db import SessionLocal

# Configuración del router
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)] # ¡Importante! Protege todas las rutas.
)

templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_class=HTMLResponse, name="admin_dashboard")
def admin_dashboard(request: Request):
    """Página principal del panel de administración."""
    tmpl = templates.get_template("admin_dashboard.html")
    return tmpl.render({"request": request})

@router.get("/feriados", response_class=HTMLResponse, name="admin_feriados")
def admin_feriados(request: Request, db: Session = Depends(get_db)):
    """Página para gestionar feriados."""
    # Por defecto, muestra el año actual
    year = datetime.now().year
    holidays = crud.get_holidays_by_year(db, year)
    
    tmpl = templates.get_template("admin_feriados.html")
    return tmpl.render({
        "request": request,
        "holidays": holidays,
        "year": year
    })

@router.post("/feriados", name="admin_create_holiday")
def admin_create_holiday(
    request: Request,
    holiday_date_str: str = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Crea un nuevo feriado."""
    try:
        holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
    except ValueError:
        # Manejar error de fecha inválida (idealmente con un mensaje de error)
        return RedirectResponse(url=router.url_path_for("admin_feriados"), status_code=303)

    # Evitar duplicados
    if not crud.get_holiday_by_date(db, holiday_date):
        crud.create_holiday(db, holiday_date=holiday_date, name=name)
        
    return RedirectResponse(url=router.url_path_for("admin_feriados"), status_code=303)

@router.post("/feriados/{holiday_id}/delete", name="admin_delete_holiday")
def admin_delete_holiday(
    request: Request,
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Elimina un feriado."""
    crud.delete_holiday(db, holiday_id=holiday_id)
    return RedirectResponse(url=router.url_path_for("admin_feriados"), status_code=303)