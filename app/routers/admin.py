# app/routers/admin.py
# (VERSIÓN CORREGIDA PARTE 3)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Dict, Any # Importar Dict, Any

from app import crud, models, schemas
from app.auth import get_current_admin_user
from app.db import SessionLocal

# Configuración del router
router = APIRouter(
    prefix="/gestion/admin", # <-- CORREGIDO CON PREFIJO
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

# --- RUTAS DE FERIADOS (DE PARTE 1) ---

@router.get("/feriados", response_class=HTMLResponse, name="admin_feriados")
def admin_feriados(request: Request, db: Session = Depends(get_db)):
    """Página para gestionar feriados."""
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
    request: Request, # <--- AÑADIDO 'request: Request'
    holiday_date_str: str = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Crea un nuevo feriado."""
    try:
        holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

    if not crud.get_holiday_by_date(db, holiday_date):
        crud.create_holiday(db, holiday_date=holiday_date, name=name)
        
    return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

@router.post("/feriados/{holiday_id}/delete", name="admin_delete_holiday")
def admin_delete_holiday(
    request: Request, # <--- AÑADIDO 'request: Request'
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Elimina un feriado."""
    crud.delete_holiday(db, holiday_id=holiday_id)
    return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

# --- NUEVAS RUTAS DE AJUSTES (PARTE 3) ---

@router.get("/ajustes", response_class=HTMLResponse, name="admin_ajustes")
def admin_ajustes_page(request: Request, db: Session = Depends(get_db)):
    """Página para gestionar los ajustes del sistema."""
    
    settings_db = crud.get_all_settings(db)
    # Convertir la lista de objetos en un diccionario clave-valor
    settings_dict = {s.key: s.value for s in settings_db}
    
    tmpl = templates.get_template("admin_ajustes.html")
    return tmpl.render({
        "request": request,
        "settings": settings_dict
    })

@router.post("/ajustes", name="admin_update_settings")
async def admin_update_settings(request: Request, db: Session = Depends(get_db)): # <--- ¡¡AQUÍ ESTÁ LA CORRECCIÓN!!
    """Actualiza los ajustes del sistema."""
    form_data = await request.form()
    
    # Iterar sobre todos los datos del formulario y guardarlos
    for key, value in form_data.items():
        crud.update_or_create_setting(db, key=key, value=value)
        
    return RedirectResponse(url=request.url_for("admin_ajustes"), status_code=303)