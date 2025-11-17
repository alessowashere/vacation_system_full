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
from app.auth import get_current_user, create_access_token, get_current_manager_user, oauth
from app.db import SessionLocal, get_db
from sqlalchemy.orm import Session
from datetime import timedelta, datetime


from app.routers import admin as admin_router
from app.routers import actions as actions_router

# app/main.py


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

app.state.oauth = oauth
@app.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    tmpl = templates.get_template("home.html")
    return tmpl.render({"request": request})

# AUTH routes
# --- RUTAS DE AUTENTICACIÓN (REESCRITAS PARA CAMINO B) ---

@app.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    """
    Muestra la página de login (que ahora solo tiene un botón).
    """
    tmpl = templates.get_template("login.html")
    # Pasamos el dominio para mostrarlo (opcional)
    return tmpl.render({
        "request": request,
        "GOOGLE_LOGIN_DOMAIN": "uandina.edu.pe" 
    })

@app.get("/login/google", name="login_google")
async def login_google(request: Request):
    """
    Paso 1: Redirige al usuario a la página de inicio de sesión de Google.
    """
    # Esta es la URL de callback que pusiste en Google Cloud
    redirect_uri = request.url_for('auth_google_callback')
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    """
    Paso 2: Google redirige al usuario de vuelta aquí después del login.
    """
    try:
        # Obtenemos el token de Google
        token = await request.app.state.oauth.google.authorize_access_token(request)
    except Exception as e:
        # El usuario canceló o hubo un error
        return RedirectResponse(url=request.url_for('login_page'))

    # Obtenemos la información del usuario (email, nombre, etc.)
    user_info = token.get('userinfo')
    if not user_info:
        return RedirectResponse(url=request.url_for('login_page'))

    user_email = user_info.get('email')
    user_domain = user_info.get('hd')

    # --- ¡LA VALIDACIÓN MÁS IMPORTANTE! ---
    # Asegurarnos de que solo entren usuarios de nuestro dominio
    if user_domain != "uandina.edu.pe":
        error_url = str(request.url_for('login_page')) + "?error=domain"
        return RedirectResponse(url=error_url, status_code=302)

    # Verificar si el usuario de Google existe en nuestra BD (cargada del CSV)
    user_in_db = db.query(models.User).filter(models.User.email == user_email).first()

    if not user_in_db:
        # El usuario es de @uandina.edu.pe pero no está en nuestra BD de RRHH.
        error_url = str(request.url_for('login_page')) + "?error=not_found"
        return RedirectResponse(url=error_url, status_code=302)

    # --- ÉXITO ---
    # El usuario es válido. Creamos nuestro propio token de sesión (JWT)
    # y lo guardamos en una cookie.
    access_token = create_access_token(data={"sub": user_in_db.email})

    response = RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="lax")
    return response

@app.get("/logout", name="logout")
def logout(request: Request):
    """
    Borra nuestra cookie de sesión.
    """
    response = RedirectResponse(url=request.url_for('home'), status_code=302)
    response.delete_cookie("access_token")
    return response

# --- FIN DE RUTAS DE AUTENTICACIÓN ---

# --- AÑADIR ESTAS RUTAS (FASE 4.2) ---


# --- FIN DE NUEVAS RUTAS ---

# RUTA DASHBOARD
@app.get("/app", response_class=HTMLResponse, name="dashboard")

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
@app.get("/vacation/{vacation_id}/submit-individual", response_class=HTMLResponse, name="vacation_submit_individual_form")
def submit_individual_form(
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
    if vacation.status != 'draft':
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)

    tmpl = templates.get_template("submission_individual_new.html")
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
# (Importar models al inicio de app/main.py si no está)
# from app import crud, models, schemas 

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

    # --- LÍNEAS NUEVAS ---
    # Buscar archivos de modificación y suspensión asociados
    mod_requests = db.query(models.ModificationRequest).filter(
        models.ModificationRequest.vacation_period_id == vacation_id
    ).all()
    sus_requests = db.query(models.SuspensionRequest).filter(
        models.SuspensionRequest.vacation_period_id == vacation_id
    ).all()
    # --- FIN DE LÍNEAS NUEVAS ---

    tmpl = templates.get_template("vacation_details.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation,
        "logs": logs,
        "mod_requests": mod_requests, # <-- NUEVO
        "sus_requests": sus_requests  # <-- NUEVO
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