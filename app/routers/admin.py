# app/routers/admin.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Dict, Any, Optional, List

from app import crud, models, schemas
from app.auth import get_current_admin_user
from app.db import SessionLocal

# Configuración del router
router = APIRouter(
    prefix="/gestion/admin", 
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)]
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

# --- RUTAS DE FERIADOS ---
@router.get("/feriados", response_class=HTMLResponse, name="admin_feriados")
def admin_feriados(request: Request, db: Session = Depends(get_db)):
    current_year = datetime.now().year
    target_year = 2026 if current_year < 2026 else current_year
    
    holidays = db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= date(target_year, 1, 1),
        models.Holiday.holiday_date <= date(target_year, 12, 31)
    ).order_by(models.Holiday.holiday_date).all()
    
    tmpl = templates.get_template("admin_feriados.html")
    return tmpl.render({"request": request, "holidays": holidays, "year": target_year})

@router.post("/feriados", name="admin_create_holiday")
def admin_create_holiday(
    request: Request, 
    holiday_date_str: str = Form(...), 
    name: str = Form(...), 
    location: str = Form(...), 
    db: Session = Depends(get_db)
):
    try:
        holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

    new_holiday = models.Holiday(
        holiday_date=holiday_date, 
        name=name, 
        location=location,
        is_national=(location == "GENERAL")
    )
    db.add(new_holiday)
    db.commit()
    
    return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

@router.post("/feriados/{holiday_id}/delete", name="admin_delete_holiday")
def admin_delete_holiday(request: Request, holiday_id: int, db: Session = Depends(get_db)):
    crud.delete_holiday(db, holiday_id=holiday_id)
    return RedirectResponse(url=request.url_for("admin_feriados"), status_code=303)

# --- RUTAS DE AJUSTES Y POLÍTICAS ---

@router.get("/ajustes", response_class=HTMLResponse, name="admin_ajustes")
def admin_ajustes_page(request: Request, db: Session = Depends(get_db)):
    settings_db = crud.get_all_settings(db)
    settings_dict = {s.key: s.value for s in settings_db}
    policies = crud.get_all_policies(db)
    
    tmpl = templates.get_template("admin_ajustes.html")
    return tmpl.render({
        "request": request,
        "settings": settings_dict,
        "policies": policies
    })

@router.post("/ajustes", name="admin_update_settings")
async def admin_update_settings(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    for key, value in form_data.items():
        crud.update_or_create_setting(db, key=key, value=value)
    return RedirectResponse(url=request.url_for("admin_ajustes"), status_code=303)

@router.post("/ajustes/policy", name="admin_create_policy")
async def admin_create_policy(
    request: Request, 
    name: str = Form(...), 
    months: list[int] = Form(...), 
    db: Session = Depends(get_db)
):
    crud.create_policy(db, name, months)
    return RedirectResponse(url=request.url_for("admin_ajustes"), status_code=303)

@router.post("/ajustes/policy/{p_id}/delete", name="admin_delete_policy")
def admin_delete_policy(request: Request, p_id: int, db: Session = Depends(get_db)):
    crud.delete_policy(db, p_id)
    return RedirectResponse(url=request.url_for("admin_ajustes"), status_code=303)

# --- GESTIÓN DE USUARIOS ---

@router.get("/users", response_class=HTMLResponse, name="admin_user_list")
def admin_user_list(request: Request, db: Session = Depends(get_db), success_msg: Optional[str] = None):
    users = crud.get_all_users(db)
    users.sort(key=lambda u: u.area if u.area else "ZZZZ")
    
    tmpl = templates.get_template("admin_user_list.html")
    return tmpl.render({"request": request, "users": users, "success_msg": success_msg})

@router.get("/users/new", response_class=HTMLResponse, name="admin_user_new")
def admin_user_new_form(request: Request, db: Session = Depends(get_db)):
    managers = crud.get_all_managers(db)
    policies = crud.get_all_policies(db)
    tmpl = templates.get_template("admin_user_form.html")
    return tmpl.render({
        "request": request, "user": None, "managers": managers, "policies": policies,
        "action_url": request.url_for("admin_user_create"), "error_msg": None
    })

@router.post("/users/new", name="admin_user_create")
async def admin_user_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    can_request_own_vacation = True if form.get("can_request_own_vacation") else False
    location = form.get("location", "CUSCO")
    username = form.get("username")
    full_name = form.get("full_name")
    email = form.get("email")
    role = form.get("role")
    area = form.get("area")
    vacation_days_total = int(form.get("vacation_days_total", 30))
    manager_id = int(form.get("manager_id")) if form.get("manager_id") else None
    vacation_policy_id = int(form.get("vacation_policy_id")) if form.get("vacation_policy_id") else None

    if crud.get_user_by_username(db, username):
        managers = crud.get_all_managers(db)
        policies = crud.get_all_policies(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request, "user": None, "managers": managers, "policies": policies,
            "action_url": request.url_for("admin_user_create"),
            "error_msg": f"El nombre de usuario '{username}' ya existe."
        }, status_code=400)
    
    try:
        user = crud.create_user(
            username=username, full_name=full_name, email=email,
            role=role, area=area, vacation_days_total=vacation_days_total, manager_id=manager_id,
            location=location,
            can_request_own_vacation=can_request_own_vacation
        )
        if vacation_policy_id:
            user.vacation_policy_id = vacation_policy_id
            db.commit()

    except ValueError as e:
        managers = crud.get_all_managers(db)
        policies = crud.get_all_policies(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request, "user": None, "managers": managers, "policies": policies,
            "action_url": request.url_for("admin_user_create"), "error_msg": str(e)
        }, status_code=400)

    return RedirectResponse(url=str(request.url_for('admin_user_list')) + f"?success_msg=Usuario creado.", status_code=303)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse, name="admin_user_edit")
def admin_user_edit_form(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user: raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    managers = crud.get_all_managers(db)
    policies = crud.get_all_policies(db)
    tmpl = templates.get_template("admin_user_form.html")
    return tmpl.render({
        "request": request, "user": user, "managers": managers, "policies": policies,
        "action_url": request.url_for("admin_user_update", user_id=user.id), "error_msg": None
    })

@router.post("/users/{user_id}/edit", name="admin_user_update")
async def admin_user_update(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user: raise HTTPException(status_code=404, detail="Usuario no encontrado")

    form = await request.form()
    location = form.get("location", "CUSCO")
    can_request_own_vacation = True if form.get("can_request_own_vacation") else False
    username = form.get("username")
    full_name = form.get("full_name")
    email = form.get("email")
    role = form.get("role")
    area = form.get("area")
    vacation_days_total = int(form.get("vacation_days_total", 30))
    manager_id = int(form.get("manager_id")) if form.get("manager_id") else None
    vacation_policy_id = int(form.get("vacation_policy_id")) if form.get("vacation_policy_id") else None

    if user.username != username and crud.get_user_by_username(db, username):
        managers = crud.get_all_managers(db)
        policies = crud.get_all_policies(db)
        tmpl = templates.get_template("admin_user_form.html")
        return tmpl.render({
            "request": request, "user": user, "managers": managers, "policies": policies,
            "action_url": request.url_for("admin_user_update", user_id=user.id),
            "error_msg": f"El usuario '{username}' ya existe."
        }, status_code=400)

    crud.admin_update_user(
        db=db, user=user, username=username, full_name=full_name, email=email,
        role=role, area=area, vacation_days_total=vacation_days_total,
        manager_id=manager_id, vacation_policy_id=vacation_policy_id,
        location=location,
        can_request_own_vacation=can_request_own_vacation
    )
    
    return RedirectResponse(url=str(request.url_for('admin_user_list')) + "?success_msg=Actualizado.", status_code=303)

@router.post("/users/{user_id}/reset-password", name="admin_user_reset_password")
def admin_user_reset_password(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    crud.admin_reset_password(db, user)
    return RedirectResponse(url=str(request.url_for('admin_user_list')) + "?success_msg=Password reseteado.", status_code=303)

# --- CORRECCIÓN DE LA REDIRECCIÓN ---
@router.get("/reports", name="admin_reports_view")
def admin_reports_view(request: Request):
    """
    Redirige usando ruta relativa '../reports/' para preservar el puerto
    del cliente (ej: 49262) sin que el proxy o FastAPI lo eliminen.
    """
    return RedirectResponse(url="../reports/", status_code=303)

@router.get("/organigrama", response_class=HTMLResponse, name="admin_org_chart")
def admin_org_chart(request: Request, db: Session = Depends(get_db)):
    users = crud.get_all_users(db)
    
    org_data = []
    for u in users:
        role_style = "color:black;"
        if u.role == "manager": role_style = "color:blue; font-weight:bold;"
        if u.role == "admin": role_style = "color:red; font-weight:bold;"
        
        node_html = f"""
            <div style="font-family: sans-serif; width: 160px; padding: 5px;">
                <div style="font-size: 14px; font-weight: bold; margin-bottom: 4px;">
                    {u.full_name or u.username}
                </div>
                <div style="{role_style} font-size: 12px;">{u.role.upper()}</div>
                <div style="color: gray; font-size: 11px; font-style: italic;">
                    {u.area or 'Sin Área'}
                </div>
            </div>
        """
        
        node_id = str(u.id)
        parent_id = str(u.manager_id) if u.manager_id else ""
        tooltip = f"{u.username} - {u.role}"
        
        org_data.append([
            {"v": node_id, "f": node_html}, 
            parent_id, 
            tooltip
        ])

    tmpl = templates.get_template("admin_org_chart.html")
    return tmpl.render({"request": request, "org_data": org_data})