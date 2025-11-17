# app/routers/admin.py
# (VERSIÓN CORREGIDA PARTE 3)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Dict, Any, Optional # <-- AÑADIR Optional

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

# ... (después de la ruta admin_update_settings)

# --- NUEVAS RUTAS DE GESTIÓN DE USUARIOS (FASE 5) ---

@router.get("/users", response_class=HTMLResponse, name="admin_user_list")
def admin_user_list(
    request: Request, 
    db: Session = Depends(get_db),
    success_msg: Optional[str] = None # Para mostrar mensajes de éxito
):
    """Muestra la lista de todos los usuarios."""
    users = crud.get_all_users(db)
    tmpl = templates.get_template("admin_user_list.html")
    return tmpl.render({
        "request": request,
        "users": users,
        "success_msg": success_msg
    })

@router.get("/users/new", response_class=HTMLResponse, name="admin_user_new")
def admin_user_new_form(request: Request, db: Session = Depends(get_db)):
    """Muestra el formulario para crear un nuevo usuario."""
    managers = crud.get_all_managers(db) # Para el dropdown de "Jefe"
    tmpl = templates.get_template("admin_user_form.html")
    return tmpl.render({
        "request": request,
        "user": None, # Indica que es un formulario de 'creación'
        "managers": managers,
        "action_url": request.url_for("admin_user_create"),
        "error_msg": None
    })

@router.post("/users/new", name="admin_user_create")
async def admin_user_create(
    request: Request, 
    db: Session = Depends(get_db)
):
    """Procesa la creación de un nuevo usuario."""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    full_name = form.get("full_name")
    email = form.get("email")
    role = form.get("role")
    area = form.get("area")
    vacation_days_total = int(form.get("vacation_days_total", 30))
    manager_id = int(form.get("manager_id")) if form.get("manager_id") else None

    # Validar que el usuario no exista
    if crud.get_user_by_username(db, username):
        managers = crud.get_all_managers(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request,
            "user": None,
            "managers": managers,
            "action_url": request.url_for("admin_user_create"),
            "error_msg": f"El nombre de usuario '{username}' ya existe."
        }, status_code=400)
    
    try:
        # Usamos SessionLocal para crear el usuario, ya que create_user la cierra
        # (Esto es por el diseño actual de create_user)
        db_session = SessionLocal()
        crud.create_user(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
            role=role,
            area=area,
            vacation_days_total=vacation_days_total,
            manager_id=manager_id
        )
        db_session.close()
    except ValueError as e:
        # Error de validación de contraseña
        managers = crud.get_all_managers(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request,
            "user": None,
            "managers": managers,
            "action_url": request.url_for("admin_user_create"),
            "error_msg": str(e)
        }, status_code=400)

    # Éxito
    success_url = request.url_for('admin_user_list') + f"?success_msg=Usuario '{username}' creado exitosamente."
    return RedirectResponse(url=success_url, status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse, name="admin_user_edit")
def admin_user_edit_form(
    request: Request, 
    user_id: int, 
    db: Session = Depends(get_db)
):
    """Muestra el formulario para editar un usuario existente."""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    managers = crud.get_all_managers(db)
    tmpl = templates.get_template("admin_user_form.html")
    return tmpl.render({
        "request": request,
        "user": user, # Pasa el usuario para rellenar el formulario
        "managers": managers,
        "action_url": request.url_for("admin_user_update", user_id=user.id),
        "error_msg": None
    })

@router.post("/users/{user_id}/edit", name="admin_user_update")
async def admin_user_update(
    request: Request, 
    user_id: int, 
    db: Session = Depends(get_db)
):
    """Procesa la actualización de un usuario."""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    form = await request.form()
    username = form.get("username")
    full_name = form.get("full_name")
    email = form.get("email")
    role = form.get("role")
    area = form.get("area")
    vacation_days_total = int(form.get("vacation_days_total", 30))
    manager_id = int(form.get("manager_id")) if form.get("manager_id") else None

    # Validar que el nuevo username (si cambió) no esté tomado
    if user.username != username and crud.get_user_by_username(db, username):
        managers = crud.get_all_managers(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request,
            "user": user,
            "managers": managers,
            "action_url": request.url_for("admin_user_update", user_id=user.id),
            "error_msg": f"El nombre de usuario '{username}' ya existe."
        }, status_code=400)

    crud.admin_update_user(
        db=db,
        user=user,
        username=username,
        full_name=full_name,
        email=email,
        role=role,
        area=area,
        vacation_days_total=vacation_days_total,
        manager_id=manager_id
    )
    
    success_url = request.url_for('admin_user_list') + f"?success_msg=Usuario '{username}' actualizado."
    return RedirectResponse(url=success_url, status_code=303)


@router.post("/users/{user_id}/reset-password", name="admin_user_reset_password")
def admin_user_reset_password(
    request: Request, 
    user_id: int, 
    db: Session = Depends(get_db)
):
    """Restablece la contraseña de un usuario a 'Temporal123!'."""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    crud.admin_reset_password(db, user)
    
    success_url = request.url_for('admin_user_list') + f"?success_msg=Contraseña de '{user.username}' restablecida a 'Temporal123!'."
    return RedirectResponse(url=success_url, status_code=303)

# --- FIN DE NUEVAS RUTAS --- 