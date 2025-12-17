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
# Importamos el COP oficial para el listado jerárquico
from app.routers.reports import COP_ORDENADO 

# Configuración del router
router = APIRouter(
    prefix="/admin", 
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

@router.get("/users/new", response_class=HTMLResponse, name="admin_user_new")
def admin_user_new_form(request: Request, db: Session = Depends(get_db)):
    managers = crud.get_all_managers(db)
    policies = crud.get_all_policies(db)
    tmpl = templates.get_template("admin_user_form.html")
    return tmpl.render({
        "request": request, "user": None, "managers": managers, "policies": policies,
        "action_url": request.url_for("admin_user_create"), "error_msg": None
    })
    
@router.get("/users", response_class=HTMLResponse, name="admin_user_list")
def admin_user_list(request: Request, db: Session = Depends(get_db), success_msg: Optional[str] = None):
    all_users = db.query(models.User).all()
    
    users_by_area = {}
    for u in all_users:
        a = (u.area or "SIN ÁREA").strip().upper()
        if a not in users_by_area: users_by_area[a] = []
        users_by_area[a].append(u)

    hierarchical_list = []
    procesados = set()

    # 1. Áreas que coinciden con el COP
    for nivel, nombre_cop in COP_ORDENADO:
        n_up = nombre_cop.upper()
        miembros = users_by_area.get(n_up, [])
        if miembros:
            procesados.add(n_up)
            hierarchical_list.append({
                "nivel": nivel, "nombre": nombre_cop, 
                "miembros": sorted(miembros, key=lambda x: (x.full_name or "").lower())
            })

    # 2. Áreas por corregir (sobrantes) - CORREGIDO PARA QUE TODOS APAREZCAN
    sobrantes = []
    for a_db, pers in users_by_area.items():
        if a_db not in procesados:
            for p in pers: p.area_erronea = a_db
            sobrantes.extend(pers)
    
    if sobrantes:
        hierarchical_list.append({
            "nivel": 99, "nombre": "OTRAS ÁREAS / POR REVISAR", 
            "miembros": sorted(sobrantes, key=lambda x: (x.full_name or "").lower())
        })

    return templates.TemplateResponse("admin_user_list.html", {
        "request": request, "hierarchy": hierarchical_list, "success_msg": success_msg
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
    is_active = True if form.get("is_active") else False
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
        can_request_own_vacation=can_request_own_vacation,
        is_active=is_active
    )
    
    return RedirectResponse(url=str(request.url_for('admin_user_list')) + "?success_msg=Actualizado.", status_code=303)

@router.post("/users/{user_id}/reset-password", name="admin_user_reset_password")
def admin_user_reset_password(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    crud.admin_reset_password(db, user)
    return RedirectResponse(url=str(request.url_for('admin_user_list')) + "?success_msg=Password reseteado.", status_code=303)

@router.get("/reports", name="admin_reports_view")
def admin_reports_view(request: Request):
    """
    Redirige usando url_for para preservar el puerto del cliente (ej: 49262)
    evitando que redirecciones absolutas lo eliminen.
    """
    return RedirectResponse(url=request.url_for('admin_reports_panel'), status_code=303)

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
                <div style="font-size: 14px; font-weight: bold; margin-bottom: 4px;">{u.full_name or u.username}</div>
                <div style="{role_style} font-size: 12px;">{u.role.upper()}</div>
                <div style="color: gray; font-size: 11px; font-style: italic;">{u.area or 'Sin Área'}</div>
            </div>
        """
        org_data.append([{"v": str(u.id), "f": node_html}, str(u.manager_id) if u.manager_id else "", u.username])

    tmpl = templates.get_template("admin_org_chart.html")
    return tmpl.render({"request": request, "org_data": org_data})