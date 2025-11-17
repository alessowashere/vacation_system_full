# app/main.py
# (VERSIÓN PARTE 10)

import os
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from app import crud, models, schemas
from app.db import SessionLocal, engine, Base
from app.auth import get_current_user, create_access_token, get_current_manager_user
from app.db import SessionLocal, get_db
from sqlalchemy.orm import Session
from datetime import timedelta, datetime

from app.routers import admin as admin_router
from app.routers import actions as actions_router

def create_default_admin():
    print("--- CHEQUEANDO USUARIO ADMIN POR DEFECTO ---")
    db = SessionLocal()
    default_admin = crud.get_user_by_username(db, "admin")
    if not default_admin:
        print("--- CREANDO USUARIO ADMIN POR DEFECTO (admin/Redlabel@) ---")
        crud.create_user("admin", "Redlabel@", role="admin")
        print("--- USUARIO ADMIN CREADO ---")
    else:
        print("--- USUARIO ADMIN YA EXISTE ---")
    db.close()

def create_test_users():
    print("--- CHEQUEANDO USUARIOS DE PRUEBA ---")
    db = SessionLocal()
    
    if not crud.get_user_by_username(db, "hr_user"):
        crud.create_user("hr_user", "Redlabel@", role="hr", full_name="RRHH User")
        print("--- CREADO USUARIO hr_user ---")

    if not crud.get_user_by_username(db, "jefe_sist"):
        crud.create_user("jefe_sist", "Redlabel@", role="manager", full_name="Jefe de Sistemas", area="Sistemas")
        print("--- CREADO USUARIO jefe_sist (manager) ---")
        
    if not crud.get_user_by_username(db, "emp_sist"):
        crud.create_user("emp_sist", "Redlabel@", role="employee", full_name="Empleado de Sistemas", area="Sistemas")
        print("--- CREADO USUARIO emp_sist (employee) ---")
        
    db.close()

def seed_initial_data():
    db = SessionLocal()
    create_default_admin()
    crud.seed_holidays(db)
    create_test_users()
    crud.seed_settings(db)
    db.close()

seed_initial_data()

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(root_path="/gestion")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY","secret"))

app.mount("/static", StaticFiles(directory="app/static"), name="static")

uploads_dir = "uploads"
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    tmpl = templates.get_template("home.html")
    return tmpl.render({"request": request})

# AUTH routes
@app.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    tmpl = templates.get_template("login.html")
    return tmpl.render({"request": request})

@app.post("/login", name="login_submit")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = crud.authenticate_user(username, password)
    if not user:
        error_url = str(request.url_for('login_page')) + "?error=1"
        return RedirectResponse(url=error_url, status_code=302)
        
    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    response.set_cookie("access_token", token, httponly=True)
    return response

@app.get("/logout", name="logout")
def logout(request: Request):
    response = RedirectResponse(url=request.url_for('home'), status_code=302)
    response.delete_cookie("access_token")
    return response

# RUTA DASHBOARD
@app.get("/app", response_class=HTMLResponse, name="dashboard")
def dashboard(
    request: Request, 
    current=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    user = current
    tmpl = templates.get_template("dashboard.html")
    data = crud.get_dashboard_data(db, user)
    
    error_msg = None
    error_type = request.query_params.get("error")
    if error_type:
        error_msg = request.query_params.get("msg", "Ocurrió un error.")
    
    return tmpl.render({
        "request": request, 
        "user": user, 
        "data": data,
        "error_msg": error_msg 
    })

# Rutas de Creación de Vacaciones
@app.get("/vacations/new", response_class=HTMLResponse, name="vacation_new_form")
def new_vacation_form(
    request: Request, 
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    remaining_balance = crud.get_user_vacation_balance(db, current)
    
    tmpl = templates.get_template("vacation_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "remaining_balance": remaining_balance 
    })

@app.post("/vacations", name="vacation_create")
async def create_vacation(
    request: Request, 
    start_date: str = Form(...), 
    period_type: int = Form(...), 
    file: UploadFile = File(None), 
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    file_path_in_db = None
    if file and file.filename: 
        uploads_dir = "uploads"
        file_path_in_db = f"{current.username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_disk_path = os.path.join(uploads_dir, file_path_in_db)
        
        with open(file_disk_path, "wb") as f:
            f.write(await file.read())
            
    try:
        vp = crud.create_vacation(db, current, start_date, period_type, file_path_in_db)
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    
    except Exception as e:
        error_str = str(e)
        error_type = "general"
        if "balance" in error_str:
            error_type = "balance"
        elif "Invalid start date" in error_str:
            error_type = "start_date"
            
        error_url = str(request.url_for('dashboard')) + f"?error={error_type}&msg={error_str}"
        return RedirectResponse(url=error_url, status_code=302)

# Ruta de Modificación (de Parte 6)
@app.get("/vacation/{vacation_id}/modify", response_class=HTMLResponse, name="vacation_modify_form")
def modify_vacation_form(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)

    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")
    if vacation.status != 'rejected':
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)

    tmpl = templates.get_template("modification_request_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation
    })

# Rutas de Edición (de Parte 8)
@app.get("/vacation/{vacation_id}/edit", response_class=HTMLResponse, name="vacation_edit_form")
def edit_vacation_form(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    
    if not crud.check_edit_permission(vacation, current):
        error_url = str(request.url_for('dashboard')) + "?error=edit_perm&msg=No tienes permiso para editar."
        return RedirectResponse(url=error_url, status_code=302)

    tmpl = templates.get_template("vacation_edit.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation
    })

@app.post("/vacation/{vacation_id}/edit", name="vacation_edit_submit")
async def edit_vacation_submit(
    request: Request,
    vacation_id: int,
    start_date: str = Form(...),
    period_type: int = Form(...),
    file: UploadFile = File(None),
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    
    if not crud.check_edit_permission(vacation, current):
        error_url = str(request.url_for('dashboard')) + "?error=edit_perm&msg=No tienes permiso para editar."
        return RedirectResponse(url=error_url, status_code=302)
    
    file_path_in_db = vacation.attached_file
    if file and file.filename: 
        uploads_dir = "uploads"
        file_path_in_db = f"{current.username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_disk_path = os.path.join(uploads_dir, file_path_in_db)
        
        with open(file_disk_path, "wb") as f:
            f.write(await file.read())
            
    try:
        crud.update_vacation_details(
            db,
            vacation=vacation,
            start_date_str=start_date,
            type_period=period_type,
            file_name=file_path_in_db,
            actor=current
        )
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    
    except Exception as e:
        error_str = str(e)
        error_type = "general"
        if "balance" in error_str:
            error_type = "balance"
        elif "Invalid start date" in error_str:
            error_type = "start_date"
            
        error_url = str(request.url_for('dashboard')) + f"?error={error_type}&msg={error_str}"
        return RedirectResponse(url=error_url, status_code=302)

# Ruta de Detalles (de Parte 9)
@app.get("/vacation/{vacation_id}/details", response_class=HTMLResponse, name="vacation_details")
def vacation_details(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    can_view = False
    if current.role in ['admin', 'hr']: can_view = True
    elif current.role == 'manager' and current.area == vacation.user.area: can_view = True
    elif current.id == vacation.user_id: can_view = True
        
    if not can_view:
        raise HTTPException(status_code=403, detail="No autorizado")

    logs = crud.get_logs_for_vacation(db, vacation_id=vacation_id)

    tmpl = templates.get_template("vacation_details.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation,
        "logs": logs
    })

# --- NUEVA RUTA (PARTE 10) ---
@app.get("/vacation/{vacation_id}/suspend", response_class=HTMLResponse, name="vacation_suspend_form")
def suspend_vacation_form(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_manager_user), # Solo managers
    db: Session = Depends(get_db)
):
    """
    Muestra el formulario para solicitar la suspensión de una vacación APROBADA.
    """
    vacation = crud.get_vacation_by_id(db, vacation_id)

    # Validar
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")
    if vacation.status != 'approved':
        # Solo se pueden suspender las aprobadas
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg=Solo se pueden suspender solicitudes APROBADAS."
        return RedirectResponse(url=error_url, status_code=302)

    tmpl = templates.get_template("suspension_request_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation
    })
# --- FIN DE NUEVA RUTA ---


# ---- INCLUIR ROUTERS ----
from app.api import api_router
app.include_router(api_router, prefix="/api")

app.include_router(admin_router.router)
app.include_router(actions_router.router)