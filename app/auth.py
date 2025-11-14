import os
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
import jwt
from datetime import datetime, timedelta
from .crud import get_user_by_username
from app.db import SessionLocal

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret")
ALGORITHM = "HS256"
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: int = 60*60*24):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        # Redirigir al login si no está autenticado
        raise HTTPException(status_code=302, detail="Not authenticated", headers={"Location": "/gestion/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=302, detail="Invalid token", headers={"Location": "/gestion/login"})
    except Exception as e:
        raise HTTPException(status_code=302, detail="Invalid token", headers={"Location": "/gestion/login"})
    db = SessionLocal()
    user = db.query(__import__("app.models", fromlist=["models"]).User).filter_by(username=username).first()
    db.close()
    if not user:
        raise HTTPException(status_code=302, detail="User not found", headers={"Location": "/gestion/login"})
    return user

# --- AÑADIR ESTAS FUNCIONES ---

def get_current_admin_user(current=Depends(get_current_user)):
    """
    Dependencia que verifica si el usuario actual es 'admin'.
    Si no lo es, lanza un error 403 (Prohibido).
    """
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Acción no autorizada: Requiere rol de Administrador")
    return current

def get_current_hr_user(current=Depends(get_current_user)):
    """
    Dependencia que verifica si el usuario actual es 'hr' o 'admin'.
    Si no lo es, lanza un error 403 (Prohibido).
    """
    if current.role not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Acción no autorizada: Requiere rol de RRHH o Administrador")
    return current

# --- FIN DE LAS NUEVAS FUNCIONES ---