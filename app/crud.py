# app/crud.py

from .db import SessionLocal
from . import models
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import os
from sqlalchemy.orm import Session
from sqlalchemy import func

# CAMBIO: Cambia "bcrypt" por "sha256_crypt".
# Esto evita usar la biblioteca bcrypt que está rota.
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def get_user_by_username(db, username):
    return db.query(models.User).filter(models.User.username==username).first()

def authenticate_user(username, password):
    db = SessionLocal()
    user = get_user_by_username(db, username)
    db.close()
    if not user:
        return None
    # Esta función (verify) funcionará automáticamente con el nuevo algoritmo
    if not pwd_context.verify(password, user.password_hash):
        return None
    return user

def create_user(username, password, role="employee", full_name=None, email=None, area=None):
    db = SessionLocal()
    # Esta función (hash) ahora usará sha256_crypt
    hashed = pwd_context.hash(password)
    u = models.User(username=username, password_hash=hashed, role=role, full_name=full_name, email=email, area=area)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u

# --- NUEVA FUNCIÓN DE BALANCE (PARTE 2) ---
def get_user_vacation_balance(db: Session, user: models.User):
    """
    Calcula y devuelve el balance de vacaciones restante para un usuario.
    El total es 30. Calcula los días ya tomados y devuelve la diferencia.
    """
    total_days_used = db.query(func.sum(models.VacationPeriod.days)).filter(
        models.VacationPeriod.user_id == user.id,
        models.VacationPeriod.status != "rejected" # Opcional: no contar rechazados
    ).scalar()
    
    # scalar() devuelve None si no hay registros, en lugar de 0
    if total_days_used is None:
        total_days_used = 0
        
    return 30 - total_days_used
# --- FIN DE NUEVA FUNCIÓN ---

# --- FUNCIÓN create_vacation MODIFICADA (PARTE 2) ---
def create_vacation(user, start_date_str, type_period, file_path=None):
    db = SessionLocal()
    
    # --- LÓGICA DE BALANCE ---
    remaining_balance = get_user_vacation_balance(db, user)
    if type_period > remaining_balance:
        db.close()
        # Devolvemos None para indicar que la creación falló
        return None 
    # --- FIN DE LÓGICA DE BALANCE ---

    sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    # Lógica de cálculo simple (se reemplazará en Parte 3)
    end = sd + timedelta(days=type_period-1)
    if end.weekday() == 4: # friday
        end = end + timedelta(days=2)
    
    # ¡Importante! 'days' debe ser el número de días que *consume* del balance,
    # que es 'type_period', no los días calendario.
    days_to_consume = type_period
    
    # Si quieres que la extensión del fin de semana cuente contra el balance,
    # descomenta la siguiente línea:
    # days_to_consume = (end - sd).days + 1
    
    vp = models.VacationPeriod(
        user_id=user.id, 
        start_date=sd, 
        end_date=end, 
        days=days_to_consume, # Usamos los días a consumir
        type_period=type_period, 
        attached_file=file_path
    )
    db.add(vp); db.commit(); db.refresh(vp); db.close()
    return vp
# --- FIN DE MODIFICACIÓN ---

def get_dashboard_data(user):
    db = SessionLocal()
    if user.role == "admin" or user.role == "hr":
        vacations = db.query(models.VacationPeriod).all()
    elif user.role == "manager":
        vacations = db.query(models.VacationPeriod).join(models.User).filter(models.User.area==user.area).all()
    else:
        vacations = db.query(models.VacationPeriod).filter(models.VacationPeriod.user_id==user.id).all()
    db.close()
    return {"vacations": vacations}

# --- LÓGICA DE FERIADOS (DE PARTE 1) ---

def get_holiday(db: Session, holiday_id: int):
    return db.query(models.Holiday).filter(models.Holiday.id == holiday_id).first()

def get_holiday_by_date(db: Session, holiday_date: date):
    return db.query(models.Holiday).filter(models.Holiday.holiday_date == holiday_date).first()

def get_holidays_by_year(db: Session, year: int):
    return db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= date(year, 1, 1),
        models.Holiday.holiday_date <= date(year, 12, 31)
    ).order_by(models.Holiday.holiday_date).all()

def create_holiday(db: Session, holiday_date: date, name: str, is_national: bool = True):
    db_holiday = models.Holiday(
        holiday_date=holiday_date, 
        name=name, 
        is_national=is_national
    )
    db.add(db_holiday)
    db.commit()
    db.refresh(db_holiday)
    return db_holiday

def delete_holiday(db: Session, holiday_id: int):
    db_holiday = get_holiday(db, holiday_id)
    if db_holiday:
        db.delete(db_holiday)
        db.commit()
    return db_holiday

def seed_holidays(db: Session):
    """
    Precarga la lista de feriados 2026 si no existen.
    """
    print("--- CHEQUEANDO FERIADOS 2026 ---")
    
    holidays_2026 = [
        {"date": date(2026, 1, 1), "name": "Año Nuevo"},
        {"date": date(2026, 4, 2), "name": "Jueves Santo"},
        {"date": date(2026, 4, 3), "name": "Viernes Santo"},
        {"date": date(2026, 5, 1), "name": "Día del Trabajo"},
        {"date": date(2026, 6, 29), "name": "San Pedro y San Pablo"},
        {"date": date(2026, 7, 23), "name": "Día de la Fuerza Aérea"},
        {"date": date(2026, 7, 28), "name": "Fiestas Patrias"},
        {"date": date(2026, 7, 29), "name": "Fiestas Patrias (segundo día)"},
        {"date": date(2026, 8, 6), "name": "Batalla de Junín"},
        {"date": date(2026, 8, 30), "name": "Santa Rosa de Lima"},
        {"date": date(2026, 10, 8), "name": "Combate de Angamos"},
        {"date": date(2026, 11, 1), "name": "Día de Todos los Santos"},
        {"date": date(2026, 12, 8), "name": "Inmaculada Concepción"},
        {"date": date(2026, 12, 9), "name": "Batalla de Ayacucho"},
        {"date": date(2026, 12, 25), "name": "Navidad"},
    ]
    
    count = 0
    for holiday in holidays_2026:
        exists = get_holiday_by_date(db, holiday["date"])
        if not exists:
            create_holiday(db, holiday["date"], holiday["name"])
            count += 1
            
    if count > 0:
        print(f"--- CREADOS {count} NUEVOS FERIADOS DE 2026 ---")
    else:
        print("--- FERIADOS 2026 YA EXISTÍAN ---")