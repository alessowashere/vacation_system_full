import os
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
import jwt
# CAMBIO 1: Importar datetime y timedelta
from datetime import datetime, timedelta
from .crud import get_user_by_username
from app.db import SessionLocal

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret")
ALGORITHM = "HS256"
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: int = 60*60*24):
    to_encode = data.copy()
    
    # CAMBIO 2: Calcular la fecha de expiración correcta
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    to_encode.update({"exp": expire})
    
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = SessionLocal()
    user = db.query(__import__("app.models", fromlist=["models"]).User).filter_by(username=username).first()
    db.close()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user