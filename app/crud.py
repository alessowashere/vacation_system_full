# app/crud.py
# (VERSIÓN PARTE 6)

from .db import SessionLocal
from . import models
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import os
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any

from app.logic.vacation_calculator import VacationCalculator

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def get_user_by_username(db, username):
    return db.query(models.User).filter(models.User.username==username).first()

def authenticate_user(username, password):
    db = SessionLocal()
    user = get_user_by_username(db, username)
    db.close()
    if not user:
        return None
    if not pwd_context.verify(password, user.password_hash):
        return None
    return user

def create_user(username, password, role="employee", full_name=None, email=None, area=None):
    db = SessionLocal()
    hashed = pwd_context.hash(password)
    u = models.User(username=username, password_hash=hashed, role=role, full_name=full_name, email=email, area=area)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u

def get_user_vacation_balance(db: Session, user: models.User):
    total_days_used = db.query(func.sum(models.VacationPeriod.days)).filter(
        models.VacationPeriod.user_id == user.id,
        models.VacationPeriod.status.in_(['draft', 'pending_hr', 'approved', 'pending_modification']) # Añadido
    ).scalar()
    
    if total_days_used is None:
        total_days_used = 0
        
    return 30 - total_days_used

def create_vacation(user: models.User, start_date_str: str, type_period: int, file_name: str = None):
    db = SessionLocal()
    
    remaining_balance = get_user_vacation_balance(db, user)
    if type_period > remaining_balance:
        db.close()
        raise Exception("Error: No tienes suficientes días de balance para esta solicitud.")
    
    calculator = VacationCalculator(db)
    
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        calculation = calculator.calculate_end_date(sd, type_period)
        
        vp = models.VacationPeriod(
            user_id=user.id,
            start_date=calculation["start_date"],
            end_date=calculation["end_date"],
            days=calculation["days_consumed"],
            type_period=type_period,
            attached_file=file_name
        )
        db.add(vp)
        db.commit()
        db.refresh(vp)
        db.close()
        return vp
        
    except ValueError as e:
        db.close()
        raise Exception(f"Error: {str(e)}")
    except Exception as e:
        db.close()
        raise Exception(f"Error inesperado: {str(e)}")

# --- get_dashboard_data MODIFICADA (PARTE 6) ---
def get_dashboard_data(db: Session, user: models.User):
    data = {}
    
    if user.role == "admin" or user.role == "hr":
        # RRHH ve todo
        data["draft_vacations"] = db.query(models.VacationPeriod).filter(
            models.VacationPeriod.status == 'draft'
        ).all()
        data["pending_vacations"] = db.query(models.VacationPeriod).filter(
            models.VacationPeriod.status == 'pending_hr'
        ).all()
        # ¡NUEVA LISTA!
        data["pending_modifications"] = db.query(models.ModificationRequest).filter(
            models.ModificationRequest.status == 'pending_review'
        ).all()
        data["finalized_vacations"] = db.query(models.VacationPeriod).filter(
            models.VacationPeriod.status.in_(['approved', 'rejected'])
        ).all()
        
    elif user.role == "manager":
        # Manager ve todas las de su área
        data["area_vacations"] = db.query(models.VacationPeriod).join(models.User).filter(
            models.User.area == user.area
        ).order_by(models.VacationPeriod.start_date).all()
        
    else:
        # Empleado solo ve las suyas
        data["my_vacations"] = db.query(models.VacationPeriod).filter(
            models.VacationPeriod.user_id == user.id
        ).order_by(models.VacationPeriod.start_date).all()
        
    return data
# --- FIN DE MODIFICACIÓN ---

def get_vacation_by_id(db: Session, vacation_id: int):
    return db.query(models.VacationPeriod).filter(models.VacationPeriod.id == vacation_id).first()

def update_vacation_status(db: Session, vacation_id: int, new_status: str):
    db_vacation = get_vacation_by_id(db, vacation_id)
    if db_vacation:
        db_vacation.status = new_status
        db.commit()
        db.refresh(db_vacation)
    return db_vacation

def submit_area_to_hr(db: Session, area: str, file_name: str):
    db.query(models.VacationPeriod).join(models.User).filter(
        models.User.area == area,
        models.VacationPeriod.status == 'draft'
    ).update(
        {
            "status": "pending_hr",
            "consolidated_doc_path": file_name
        }, 
        synchronize_session=False
    )
    db.commit()

def delete_vacation_period(db: Session, vacation_id: int):
    db_vacation = get_vacation_by_id(db, vacation_id)
    if db_vacation and db_vacation.status == 'draft':
        db.delete(db_vacation)
        db.commit()
    return db_vacation

# --- LÓGICA DE FERIADOS (Sin cambios) ---
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
    db_holiday = models.Holiday(holiday_date=holiday_date, name=name, is_national=is_national)
    db.add(db_holiday); db.commit(); db.refresh(db_holiday)
    return db_holiday
def delete_holiday(db: Session, holiday_id: int):
    db_holiday = get_holiday(db, holiday_id)
    if db_holiday:
        db.delete(db_holiday); db.commit()
    return db_holiday
def seed_holidays(db: Session):
    print("--- CHEQUEANDO FERIADOS 2026 ---")
    holidays_2026 = [
        {"date": date(2026, 1, 1), "name": "Año Nuevo"}, {"date": date(2026, 4, 2), "name": "Jueves Santo"},
        {"date": date(2026, 4, 3), "name": "Viernes Santo"}, {"date": date(2026, 5, 1), "name": "Día del Trabajo"},
        {"date": date(2026, 6, 29), "name": "San Pedro y San Pablo"}, {"date": date(2026, 7, 23), "name": "Día de la Fuerza Aérea"},
        {"date": date(2026, 7, 28), "name": "Fiestas Patrias"}, {"date": date(2026, 7, 29), "name": "Fiestas Patrias (segundo día)"},
        {"date": date(2026, 8, 6), "name": "Batalla de Junín"}, {"date": date(2026, 8, 30), "name": "Santa Rosa de Lima"},
        {"date": date(2026, 10, 8), "name": "Combate de Angamos"}, {"date": date(2026, 11, 1), "name": "Día de Todos los Santos"},
        {"date": date(2026, 12, 8), "name": "Inmaculada Concepción"}, {"date": date(2026, 12, 9), "name": "Batalla de Ayacucho"},
        {"date": date(2026, 12, 25), "name": "Navidad"},
    ]
    count = 0
    for holiday in holidays_2026:
        if not get_holiday_by_date(db, holiday["date"]):
            create_holiday(db, holiday["date"], holiday["name"]); count += 1
    if count > 0: print(f"--- CREADOS {count} NUEVOS FERIADOS DE 2026 ---")
    else: print("--- FERIADOS 2026 YA EXISTÍAN ---")

# --- LÓGICA DE AJUSTES (Sin cambios) ---
def get_setting(db: Session, key: str):
    return db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
def get_all_settings(db: Session):
    return db.query(models.SystemConfig).all()
def update_or_create_setting(db: Session, key: str, value: str, description: str = None):
    db_setting = get_setting(db, key)
    if db_setting: db_setting.value = value
    else: db_setting = models.SystemConfig(key=key, value=value, description=description); db.add(db_setting)
    db.commit(); db.refresh(db_setting)
    return db_setting
def seed_settings(db: Session):
    print("--- CHEQUEANDO AJUSTES DEL SISTEMA ---")
    default_settings = [
        {"key": "HOLIDAYS_COUNT", "value": "True", "desc": "¿Feriados cuentan contra balance?"},
        {"key": "FRIDAY_EXTENDS", "value": "True", "desc": "¿Extender si termina viernes?"},
        {"key": "ALLOW_START_ON_HOLIDAY", "value": "False", "desc": "¿Permitir iniciar en feriado?"},
        {"key": "ALLOW_START_ON_WEEKEND", "value": "False", "desc": "¿Permitir iniciar en fin de semana?"},
    ]
    count = 0
    for setting in default_settings:
        if not get_setting(db, setting["key"]):
            update_or_create_setting(db, setting["key"], setting["value"], setting["desc"]); count += 1
    if count > 0: print(f"--- CREADOS {count} AJUSTES POR DEFECTO ---")
    else: print("--- AJUSTES YA EXISTÍAN ---")

# --- NUEVAS FUNCIONES CRUD (PARTE 6) ---

def create_modification_request(
    db: Session, 
    vacation_id: int, 
    user: models.User, 
    reason: str, 
    file_name: str
):
    """Crea la solicitud y actualiza el estado de la vacación original."""
    
    # 1. Crear la solicitud de modificación
    mod_req = models.ModificationRequest(
        vacation_period_id=vacation_id,
        requesting_user_id=user.id,
        reason_text=reason,
        attached_doc_path=file_name,
        status="pending_review"
    )
    db.add(mod_req)
    
    # 2. Actualizar la vacación original
    # Su estado cambia a 'pending_modification' para que salga del pool de 'rejected'
    update_vacation_status(db, vacation_id=vacation_id, new_status="pending_modification")
    
    db.commit()
    db.refresh(mod_req)
    return mod_req

def get_modification_by_id(db: Session, mod_id: int):
    """Obtiene una solicitud de modificación por su ID."""
    return db.query(models.ModificationRequest).filter(models.ModificationRequest.id == mod_id).first()

def approve_modification(db: Session, mod_id: int):
    """
    Aprueba la solicitud:
    1. Marca la solicitud como 'approved'.
    2. Devuelve la vacación original a 'draft' para que el jefe la edite/re-envíe.
    """
    mod_req = get_modification_by_id(db, mod_id)
    if not mod_req:
        return None
        
    mod_req.status = "approved"
    # Devuelve la vacación original a 'draft'
    update_vacation_status(db, vacation_id=mod_req.vacation_period_id, new_status="draft")
    
    db.commit()
    return mod_req

def reject_modification(db: Session, mod_id: int):
    """
    Rechaza la solicitud:
    1. Marca la solicitud como 'rejected'.
    2. Devuelve la vacación original a 'rejected' (donde estaba).
    """
    mod_req = get_modification_by_id(db, mod_id)
    if not mod_req:
        return None
        
    mod_req.status = "rejected"
    # Devuelve la vacación original a 'rejected'
    update_vacation_status(db, vacation_id=mod_req.vacation_period_id, new_status="rejected")
    
    db.commit()
    return mod_req