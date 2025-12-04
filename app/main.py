# app/main.py
# (VERSIÓN ACTUALIZADA CON ASIGNACIÓN POR JEFE)

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
from typing import Optional # <-- IMPORTANTE AÑADIR ESTO
from app.utils.email import send_email_async # <-- Asegúrate de importar esto

from app.routers import admin as admin_router
from app.routers import actions as actions_router

def seed_initial_data():
    db = SessionLocal()
    crud.seed_holidays(db)
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

# --- RUTAS DE AUTENTICACIÓN ---
@app.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    tmpl = templates.get_template("home.html")
    return tmpl.render({"request": request})

@app.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    tmpl = templates.get_template("login.html")
    return tmpl.render({
        "request": request,
        "GOOGLE_LOGIN_DOMAIN": "uandina.edu.pe" 
    })

@app.get("/login/google", name="login_google")
async def login_google(request: Request):
    redirect_uri = request.url_for('auth_google_callback')
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await request.app.state.oauth.google.authorize_access_token(request)
    except Exception as e:
        return RedirectResponse(url=request.url_for('login_page'))

    user_info = token.get('userinfo')
    if not user_info:
        return RedirectResponse(url=request.url_for('login_page'))

    user_email = user_info.get('email')
    user_domain = user_info.get('hd')

    if user_domain != "uandina.edu.pe":
        error_url = str(request.url_for('login_page')) + "?error=domain"
        return RedirectResponse(url=error_url, status_code=302)

    user_in_db = db.query(models.User).filter(models.User.email == user_email).first()

    if not user_in_db:
        error_url = str(request.url_for('login_page')) + "?error=not_found"
        return RedirectResponse(url=error_url, status_code=302)

    access_token = create_access_token(data={"sub": user_in_db.email})

    response = RedirectResponse(url=request.url_for('dashboard'), status_code=302)
    response.set_cookie("access_token", access_token, httponly=True, secure=False, samesite="lax")
    return response

@app.get("/logout", name="logout")
def logout(request: Request):
    response = RedirectResponse(url=request.url_for('home'), status_code=302)
    response.delete_cookie("access_token")
    return response

# --- RUTAS PRINCIPALES ---

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

@app.get("/vacations/new", response_class=HTMLResponse, name="vacation_new_form")
def new_vacation_form(
    request: Request, 
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    remaining_balance = crud.get_user_vacation_balance(db, current)
    
    # --- LOGICA PARA MOSTRAR EMPLEADOS A JEFES/ADMINS ---
    employees = []
    if current.role in ['admin', 'hr']:
        employees = crud.get_all_users(db)
    elif current.role == 'manager':
        # El manager solo ve a sus subordinados
        employees = current.subordinates 
    # ----------------------------------------------------

    tmpl = templates.get_template("vacation_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "remaining_balance": remaining_balance,
        "employees": employees  # Pasamos la lista a la plantilla
    })

@app.post("/vacations", name="vacation_create")
async def create_vacation(
    request: Request, 
    start_date: str = Form(...), 
    period_type: int = Form(...), 
    target_user_id: Optional[int] = Form(None),
    file: UploadFile = File(None), # <-- YA ES OPCIONAL AQUÍ, ESTÁ BIEN
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    # Por defecto, la vacación es para quien la crea
    user_to_create_for = current

    # --- LOGICA DE ASIGNACIÓN ---
    if target_user_id:
        # Validar permisos
        if current.role == 'employee':
             # Un empleado normal no puede asignar a otros
             error_url = str(request.url_for('dashboard')) + "?error=auth&msg=No tienes permiso para asignar vacaciones a otros."
             return RedirectResponse(url=error_url, status_code=302)
        
        target_user = crud.get_user_by_id(db, target_user_id)
        if not target_user:
             error_url = str(request.url_for('dashboard')) + "?error=not_found&msg=Usuario destino no encontrado."
             return RedirectResponse(url=error_url, status_code=302)

        if current.role == 'manager':
            # Verificar que el target_user sea realmente subordinado de este manager
            if target_user.manager_id != current.id:
                 error_url = str(request.url_for('dashboard')) + "?error=auth&msg=Este usuario no es tu subordinado."
                 return RedirectResponse(url=error_url, status_code=302)
        
        # Si pasa las validaciones, cambiamos el usuario objetivo
        user_to_create_for = target_user
    # ----------------------------

    file_path_in_db = None
    if file and file.filename: 
        uploads_dir = "uploads"
        file_path_in_db = f"{user_to_create_for.username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_disk_path = os.path.join(uploads_dir, file_path_in_db)
        
        with open(file_disk_path, "wb") as f:
            f.write(await file.read())
            
    try:
        vp = crud.create_vacation(db, user_to_create_for, start_date, period_type, file_path_in_db)
        
        if user_to_create_for.id != current.id:
            crud.create_vacation_log(db, vp, current, f"Solicitud creada por el jefe/admin: {current.username}")
        manager = user_to_create_for.manager
        if manager and manager.email:
            approval_link = str(request.url_for('login_page')) # O link directo al dashboard
            
            await send_email_async(
                subject=f"NUEVA SOLICITUD DE VACACIONES - {user_to_create_for.full_name}",
                email_to=[manager.email],
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3 style="color: #2c3e50;">PROCESO DE VACACIONES 2026</h3>
                    <p>El colaborador <b>{user_to_create_for.full_name}</b> ha registrado una solicitud.</p>
                    <ul>
                        <li><b>Inicio:</b> {start_date}</li>
                        <li><b>Días:</b> {period_type}</li>
                    </ul>
                    <p>Por favor, ingresa al sistema para revisar y tramitar.</p>
                    <a href="{approval_link}" style="background-color:#3498db; color:white; padding:10px 15px; text-decoration:none; border-radius:5px;">Ir al Sistema</a>
                </div>
                """
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
    
    # --- CORRECCIÓN AQUÍ ---
    # Antes: if vacation.user.area != current.area:
    # Ahora verificamos si es Admin O si es el Jefe directo
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado: No eres el jefe directo de este usuario.")
    # -----------------------

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
    
    # --- CORRECCIÓN AQUÍ ---
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado: No eres el jefe directo.")
    # -----------------------

    if vacation.status != 'draft':
        return RedirectResponse(url=request.url_for('dashboard'), status_code=302)

    tmpl = templates.get_template("submission_individual_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation
    })

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
    elif current.role == 'manager' and vacation.user.manager_id == current.id: can_view = True
    elif current.id == vacation.user_id: can_view = True

    if not can_view:
        raise HTTPException(status_code=403, detail="No autorizado")

    logs = crud.get_logs_for_vacation(db, vacation_id=vacation_id)

    mod_requests = db.query(models.ModificationRequest).filter(
        models.ModificationRequest.vacation_period_id == vacation_id
    ).all()
    sus_requests = db.query(models.SuspensionRequest).filter(
        models.SuspensionRequest.vacation_period_id == vacation_id
    ).all()

    tmpl = templates.get_template("vacation_details.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation,
        "logs": logs,
        "mod_requests": mod_requests,
        "sus_requests": sus_requests
    })

@app.get("/vacation/{vacation_id}/suspend", response_class=HTMLResponse, name="vacation_suspend_form")
def suspend_vacation_form(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_manager_user), 
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)

    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    # --- CORRECCIÓN AQUÍ ---
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    # -----------------------

    if vacation.status != 'approved':
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg=Solo se pueden suspender solicitudes APROBADAS."
        return RedirectResponse(url=error_url, status_code=302)

    tmpl = templates.get_template("suspension_request_new.html")
    return tmpl.render({
        "request": request, 
        "user": current,
        "vacation": vacation
    })

# ---- INCLUIR ROUTERS ----
from app.api import api_router
app.include_router(api_router, prefix="/api")

app.include_router(admin_router.router)
app.include_router(actions_router.router)