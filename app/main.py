# app/main.py

import os
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from app import crud, models, schemas
from app.db import SessionLocal, engine, Base
from app.auth import get_current_user, create_access_token
from datetime import timedelta, datetime # Importar datetime

# --- IMPORTA EL ROUTER DE ADMIN (DE PARTE 1) ---
from app.routers import admin as admin_router

# CAMBIO: Vuelve a activar la creación del admin.
# Ahora que las dependencias están arregladas, esto funcionará.
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

# --- NUEVA FUNCIÓN (PARTE 2) ---
def create_test_users():
    """
    Crea usuarios de prueba para 'hr', 'boss' (manager) y 'employee'.
    """
    print("--- CHEQUEANDO USUARIOS DE PRUEBA ---")
    db = SessionLocal()
    
    # Usuario HR
    if not crud.get_user_by_username(db, "hr_user"):
        crud.create_user("hr_user", "Redlabel@", role="hr", full_name="RRHH User")
        print("--- CREADO USUARIO hr_user ---")

    # Usuario Boss (Manager)
    if not crud.get_user_by_username(db, "jefe_sist"):
        crud.create_user("jefe_sist", "Redlabel@", role="manager", full_name="Jefe de Sistemas", area="Sistemas")
        print("--- CREADO USUARIO jefe_sist (manager) ---")
        
    # Usuario Employee
    if not crud.get_user_by_username(db, "emp_sist"):
        crud.create_user("emp_sist", "Redlabel@", role="employee", full_name="Empleado de Sistemas", area="Sistemas")
        print("--- CREADO USUARIO emp_sist (employee) ---")
        
    db.close()
# --- FIN DE NUEVA FUNCIÓN ---

# --- FUNCIÓN DE INICIO MODIFICADA (PARTE 2) ---
def seed_initial_data():
    db = SessionLocal()
    create_default_admin()
    crud.seed_holidays(db) # De Parte 1
    create_test_users()    # De Parte 2
    db.close()

# Ejecuta ambas funciones de precarga
seed_initial_data()
# FIN DEL CAMBIO

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(root_path="/gestion")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY","secret"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    tmpl = templates.get_template("home.html")
    return tmpl.render({"request": request})

# AUTH routes (simple forms)
@app.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    tmpl = templates.get_template("login.html")
    return tmpl.render({"request": request})

@app.post("/login", name="login_submit")
def login(username: str = Form(...), password: str = Form(...)):
    user = crud.authenticate_user(username, password)
    if not user:
        return RedirectResponse("/gestion/login?error=1", status_code=302) # Corregido con prefijo
    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url="/gestion/app", status_code=302) # Corregido con prefijo
    response.set_cookie("access_token", token, httponly=True)
    return response

@app.get("/logout", name="logout")
def logout():
    response = RedirectResponse("/gestion/", status_code=302) # Corregido con prefijo
    response.delete_cookie("access_token")
    return response

# --- RUTA DASHBOARD MODIFICADA (PARTE 2) ---
@app.get("/app", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, current=Depends(get_current_user)):
    user = current
    tmpl = templates.get_template("dashboard.html")
    data = crud.get_dashboard_data(user)
    
    # --- AÑADIR ESTO PARA MOSTRAR ERROR DE BALANCE ---
    # Revisa si la URL tiene un parámetro 'error'
    error_msg = None
    if request.query_params.get("error") == "balance":
        error_msg = "Error: No tienes suficientes días de balance para esta solicitud."
    
    return tmpl.render({
        "request": request, 
        "user": user, 
        "data": data,
        "error_msg": error_msg # <-- Pasa el mensaje de error a la plantilla
    })
# --- FIN DE MODIFICACIÓN ---

# --- RUTA vacation_new_form MODIFICADA (PARTE 2) ---
@app.get("/vacations/new", response_class=HTMLResponse, name="vacation_new_form")
def new_vacation_form(request: Request, current=Depends(get_current_user)):
    # --- OBTENER EL BALANCE ---
    db = SessionLocal()
    remaining_balance = crud.get_user_vacation_balance(db, current)
    db.close()
    # --- FIN DE OBTENER BALANCE ---
    
    tmpl = templates.get_template("vacation_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "remaining_balance": remaining_balance # <-- Pasa el balance a la plantilla
    })
# --- FIN DE MODIFICACIÓN ---

# --- RUTA vacation_create MODIFICADA (PARTE 2) ---
@app.post("/vacations", name="vacation_create")
async def create_vacation(request: Request, start_date: str = Form(...), period_type: int = Form(...), file: UploadFile = File(None), current=Depends(get_current_user)):
    # save file if provided
    file_path = None
    if file and file.filename: # Asegurarse que file.filename no esté vacío
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, f"{current.username}_{file.filename}")
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
    # --- LÓGICA DE CREACIÓN MODIFICADA ---
    vp = crud.create_vacation(current, start_date, period_type, file_path)
    
    if vp is None:
        # La creación falló (falta de balance)
        # Redirigir al dashboard con un mensaje de error
        return RedirectResponse("/gestion/app?error=balance", status_code=302) # Corregido con prefijo
    
    # Todo salió bien
    return RedirectResponse("/gestion/app", status_code=302) # Corregido con prefijo
    # --- FIN DE MODIFICACIÓN ---

# simple API endpoints
from app.api import api_router
app.include_router(api_router, prefix="/api")

# --- AÑADE EL ROUTER DE ADMIN (DE PARTE 1) ---
app.include_router(admin_router.router)