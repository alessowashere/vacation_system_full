# app/auth.py
# (VERSIÓN PARTE 4)

import os
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
import jwt
from datetime import datetime, timedelta
from app.db import SessionLocal, get_db # <-- AÑADIR get_db
from sqlalchemy.orm import Session # <-- AÑADIR Session
from app import models # <-- AÑADIR importación de models

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret")
ALGORITHM = "HS256"
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: int = 60*60*24):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Dependencia principal:
    1. Obtiene el token de la cookie.
    2. Valida el token y obtiene el usuario de la BD.
    3. (NUEVO) Verifica si el usuario debe cambiar su contraseña.
    4. (NUEVO) Si es así, redirige a la página de cambio, bloqueando todo lo demás.
    """
    token = request.cookies.get("access_token")
    login_url = request.url_for('login_page')
    
    if not token:
        raise HTTPException(status_code=302, detail="Not authenticated", headers={"Location": login_url})
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=302, detail="Invalid token", headers={"Location": login_url})
    except Exception as e:
        raise HTTPException(status_code=302, detail="Invalid token", headers={"Location": login_url})

    # Usar la sesión de BD inyectada
    user = db.query(models.User).filter_by(username=username).first()
    
    if not user:
        raise HTTPException(status_code=302, detail="User not found", headers={"Location": login_url})

    # --- INICIO DE LÓGICA FASE 4.2 ---
    
    # Rutas a las que SÍ se puede acceder durante el cambio forzado
    current_path = request.url.path
    allowed_paths = ["/gestion/change-password", "/gestion/logout"]
    
    is_allowed = False
    for path in allowed_paths:
        if current_path.startswith(path):
            is_allowed = True
            break
            
    if user.force_password_change and not is_allowed:
        # Si el usuario está forzado a cambiar y NO está en una de las páginas permitidas
        
        # Usamos la ruta hardcoded por seguridad (url_for puede fallar en el arranque)
        redirect_url = "/gestion/change-password" 
        
        raise HTTPException(
            status_code=302, 
            detail="Debe cambiar su contraseña", 
            headers={"Location": redirect_url}
        )
    # --- FIN DE LÓGICA FASE 4.2 ---

    return user

# --- AÑADIR ESTAS FUNCIONES ---

def get_current_admin_user(current=Depends(get_current_user)):
    """
    Dependencia que verifica si el usuario actual es 'admin'.
    """
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Acción no autorizada: Requiere rol de Administrador")
    return current

def get_current_hr_user(current=Depends(get_current_user)):
    """
    Dependencia que verifica si el usuario actual es 'hr' o 'admin'.
    """
    if current.role not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Acción no autorizada: Requiere rol de RRHH o Administrador")
    return current

def get_current_manager_user(current=Depends(get_current_user)):
    """
    Dependencia que verifica si el usuario actual es 'manager' o 'admin'.
    """
    if current.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Acción no autorizada: Requiere rol de Manager o Administrador")
    return current
# --- FIN DE LAS MODIFICACIONES DE ROL ---