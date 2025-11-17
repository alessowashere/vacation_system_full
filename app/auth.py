# app/auth.py
# (REESCRITO PARA GOOGLE OAUTH - CAMINO B)

import os
from fastapi import Depends, HTTPException, Request
import jwt
from datetime import datetime, timedelta
from app.db import get_db
from sqlalchemy.orm import Session
from app import models, crud
from authlib.integrations.starlette_client import OAuth

# Clave secreta para firmar nuestro propio token de sesión (JWT)
# NO es el secreto de Google.
SECRET_KEY = os.getenv("SECRET_KEY", "un-secreto-muy-seguro-para-jwt")
ALGORITHM = "HS256"

# Configuración de Authlib para Google
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account' # Opcional: siempre pregunta qué cuenta usar
    }
)

def create_access_token(data: dict, expires_delta: int = 60*60*24):
    """
    Crea nuestro token de sesión interno (JWT) después de que Google nos valide.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Dependencia principal de autenticación.
    1. Lee nuestro token de sesión (JWT) de la cookie.
    2. Valida el token.
    3. Busca al usuario en la BD por el email/ID guardado en el token.
    """
    token = request.cookies.get("access_token")
    login_url = request.url_for('login_page')
    
    if not token:
        raise HTTPException(status_code=302, detail="No autenticado", headers={"Location": login_url})
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub") # Estamos guardando el email en 'sub'
        if user_email is None:
            raise HTTPException(status_code=302, detail="Token inválido", headers={"Location": login_url})
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=302, detail="Sesión expirada", headers={"Location": login_url})
    except Exception as e:
        raise HTTPException(status_code=302, detail="Token inválido", headers={"Location": login_url})

    # Busca al usuario en nuestra BD usando el email validado por Google
    user = db.query(models.User).filter(models.User.email == user_email).first()
    
    if not user:
        # Esto puede pasar si un empleado válido de Google intenta entrar
        # pero no ha sido creado en nuestra BD por el Admin.
        print(f"ALERTA: Usuario {user_email} autenticado por Google, pero no encontrado en la BD.")
        raise HTTPException(status_code=302, detail="Usuario no autorizado", headers={"Location": login_url})

    return user

# --- Funciones de Roles (Dependen de get_current_user) ---
# (Estas no necesitan cambios)

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