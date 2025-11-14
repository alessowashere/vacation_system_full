# app/main.py
# (VERSIÓN PARTE 6)

import os
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from app import crud, models, schemas
from app.db import SessionLocal, engine, Base
from app.auth import get_current_user, create_access_token, get_current_manager_user
from datetime import timedelta, datetime

# --- IMPORTA LOS ROUTERS ---
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
    crud.seed_holidays(db) # De Parte 1
    create_test_users()    # De Parte 2
    crud.seed_settings(db) # De Parte 3
    db.close()

# Ejecuta todas las funciones de precarga
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
        error_url = request.url_for('login_page') + "?error=1"
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
def dashboard(request: Request, current=Depends(get_current_user)):
    user = current
    tmpl = templates.get_template("dashboard.html")
    db = SessionLocal()
    data = crud.get_dashboard_data(db, user) # 'data' ahora es un dict con listas
    db.close()
    
    error_msg = None
    error_type = request.query_params.get("error")
    if error_type == "balance":
        error_msg = "Error: No tienes suficientes días de balance para esta solicitud."
    elif error_type == "start_date":
        error_msg = "Error: La fecha de inicio no es válida (es fin de semana o feriado)."
    elif error_type == "general":
        error_msg = "Error: Ocurrió un problema al crear la solicitud."
    
    return tmpl.render({
        "request": request, 
        "user": user, 
"data": data,
        "error_msg": error_msg 
    })

# Rutas de Creación de Vacaciones
@app.get("/vacations/new", response_class=HTMLResponse, name="vacation_new_form")
def new_vacation_form(request: Request, current=Depends(get_current_user)):
    db = SessionLocal()
    remaining_balance = crud.get_user_vacation_balance(db, current)
    db.close()
    
    tmpl = templates.get_template("vacation_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "remaining_balance": remaining_balance 
    })

@app.post("/vacations", name="vacation_create")
async def create_vacation(request: Request, start_date: str = Form(...), period_type: int = Form(...), file: UploadFile = File(None), current=Depends(get_current_user)):
    
    file_path_in_db = None
    if file and file.filename: 
        uploads_dir = "uploads"
        file_path_in_db = f"{current.username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_disk_path = os.path.join(uploads_dir, file_path_in_db)
        
        with open(file_disk_path, "wb") as f:
            f.write(await file.read())
            
    try:
        vp = crud.create_vacation(current, start_date, period_type, file_path_in_db)
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    
    except Exception as e:
        error_str = str(e)
        error_type = "general"
        if "balance" in error_str:
            error_type = "balance"
        elif "Invalid start date" in error_str:
            error_type = "start_date"
            
        error_url = request.url_for('dashboard') + f"?error={error_type}"
        return RedirectResponse(url=error_url, status_code=302)

# --- NUEVA RUTA (PARTE 6) ---
@app.get("/vacation/{vacation_id}/modify", response_class=HTMLResponse, name="vacation_modify_form")
def modify_vacation_form(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_manager_user) # Solo managers
):
    """
    Muestra el formulario para solicitar la modificación de una solicitud rechazada.
    """
    db = SessionLocal()
    vacation = crud.get_vacation_by_id(db, vacation_id)
    db.close()

    # Validar
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")
    if vacation.status != 'rejected':
        # Solo se pueden modificar las rechazadas
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)

    tmpl = templates.get_template("modification_request_new.html")
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