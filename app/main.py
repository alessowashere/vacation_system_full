import os
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from app import crud, models, schemas
from app.db import SessionLocal, engine, Base
from app.auth import get_current_user, create_access_token
from datetime import timedelta


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

create_default_admin()
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
        return RedirectResponse("/login?error=1", status_code=302)
    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url="/app", status_code=302)
    response.set_cookie("access_token", token, httponly=True)
    return response

@app.get("/logout", name="logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("access_token")
    return response

@app.get("/app", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, current=Depends(get_current_user)):
    user = current
    tmpl = templates.get_template("dashboard.html")
    data = crud.get_dashboard_data(user)
    return tmpl.render({"request": request, "user": user, "data": data})

# simple create vacation form
@app.get("/vacations/new", response_class=HTMLResponse, name="vacation_new_form")
def new_vacation_form(request: Request, current=Depends(get_current_user)):
    tmpl = templates.get_template("vacation_new.html")
    return tmpl.render({"request": request, "user": current})

@app.post("/vacations", name="vacation_create")
async def create_vacation(request: Request, start_date: str = Form(...), period_type: int = Form(...), file: UploadFile = File(None), current=Depends(get_current_user)):
    # save file if provided
    file_path = None
    if file:
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, f"{current.username}_{file.filename}")
        with open(file_path, "wb") as f:
            f.write(await file.read())
    vp = crud.create_vacation(current, start_date, period_type, file_path)
    return RedirectResponse("/app", status_code=302)

# simple API endpoints
from app.api import api_router
app.include_router(api_router, prefix="/api")