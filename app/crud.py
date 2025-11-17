# app/crud.py
# (VERSIÓN PARTE 10)
import re # <-- AÑADIR ESTA LÍNEA
from .db import SessionLocal, get_db
from . import models
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import os
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Dict, Any

from app.logic.vacation_calculator import VacationCalculator
from passlib.context import CryptContext
from datetime import datetime, timedelta, date # <-- ASEGÚRATE QUE 'date' ESTÉ IMPORTADO
import os
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_ # <-- AÑADIR 'and_'
from typing import List, Dict, Any

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

# --- FIN DE LA FUNCIÓN ---
def get_user_by_username(db, username):
    return db.query(models.User).filter(models.User.username==username).first()



def create_user(username, password, role="employee", full_name=None, email=None, area=None, vacation_days_total=30, manager_id=None):
    
    # --- MODIFICACIÓN FASE 5.1 ---
    # Ahora la validación SÍ lanza un error,
    validate_password(password)
    # --- FIN DE LA MODIFICACIÓN ---

    db = SessionLocal()
    hashed = pwd_context.hash(password)
    # El 'force_password_change' se quedará en True por defecto
    u = models.User(
        username=username, 
        password_hash=hashed, 
        role=role, 
        full_name=full_name, 
        email=email, 
        area=area,
        vacation_days_total=vacation_days_total, # <-- NUEVO
        manager_id=manager_id # <-- NUEVO
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u

# --- MODIFICAR get_user_vacation_balance (FASE 5.3) ---
def get_user_vacation_balance(db: Session, user: models.User):
    total_days_used = db.query(func.sum(models.VacationPeriod.days)).filter(
        models.VacationPeriod.user_id == user.id,
        models.VacationPeriod.status.in_(['draft', 'pending_hr', 'approved', 'pending_modification'])
    ).scalar()
    
    if total_days_used is None:
        total_days_used = 0
        
    # Usar el total del usuario en lugar de 30
    return user.vacation_days_total - total_days_used
# --- FIN DE MODIFICACIÓN ---

def create_vacation_log(db: Session, vacation: models.VacationPeriod, user: models.User, log_text: str):
    log = models.VacationLog(
        vacation_period_id=vacation.id,
        user_id=user.id,
        log_text=log_text
    )
    db.add(log)
    db.commit()

def get_logs_for_vacation(db: Session, vacation_id: int):
    return db.query(models.VacationLog).options(
        joinedload(models.VacationLog.user)
    ).filter(
        models.VacationLog.vacation_period_id == vacation_id
    ).order_by(models.VacationLog.created_at.desc()).all()

def create_vacation(
    db: Session,
    user: models.User, 
    start_date_str: str, 
    type_period: int, 
    file_name: str = None
):
    remaining_balance = get_user_vacation_balance(db, user)
    if type_period > remaining_balance:
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
        
        create_vacation_log(db, vp, user, f"Solicitud creada en estado 'draft'.")
        
        return vp
        
    except ValueError as e:
        raise Exception(f"Error: {str(e)}")
    except Exception as e:
        raise Exception(f"Error inesperado: {str(e)}")

# --- get_dashboard_data MODIFICADA (PARTE 10) ---
# --- get_dashboard_data MODIFICADA (FASE 3) ---
def get_dashboard_data(db: Session, user: models.User):
    data = {}
    today = date.today()
    
    if user.role == "admin" or user.role == "hr":
        data["draft_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).filter(models.VacationPeriod.status == 'draft').all()
        
        data["pending_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).filter(models.VacationPeriod.status == 'pending_hr').all()
        
        data["pending_modifications"] = db.query(models.ModificationRequest).options(
            joinedload(models.ModificationRequest.requesting_user),
            joinedload(models.ModificationRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).filter(models.ModificationRequest.status == 'pending_review').all()
        
        data["pending_suspensions"] = db.query(models.SuspensionRequest).options(
            joinedload(models.SuspensionRequest.requesting_user),
            joinedload(models.SuspensionRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).filter(models.SuspensionRequest.status == 'pending_review').all()

        data["finalized_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).filter(
            models.VacationPeriod.status.in_(['approved', 'rejected', 'suspended'])
        ).all()
        
        # --- NUEVO (FASE 3.2) ---
        data["upcoming_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).filter(
            models.VacationPeriod.status == 'approved',
            models.VacationPeriod.start_date > today
        ).order_by(models.VacationPeriod.start_date).all()
        
    elif user.role == "manager":
        # --- MODIFICADO (FASE 3.1): Replicar lógica de HR filtrada por área ---
        
        data["draft_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).join(models.User).filter(
            models.User.area == user.area,
            models.VacationPeriod.status == 'draft'
        ).all()
        
        data["pending_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).join(models.User).filter(
            models.User.area == user.area,
            models.VacationPeriod.status == 'pending_hr'
        ).all()
        
        data["pending_modifications"] = db.query(models.ModificationRequest).options(
            joinedload(models.ModificationRequest.requesting_user),
            joinedload(models.ModificationRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).join(models.VacationPeriod).join(models.User).filter(
            models.User.area == user.area,
            models.ModificationRequest.status == 'pending_review'
        ).all()
        
        data["pending_suspensions"] = db.query(models.SuspensionRequest).options(
            joinedload(models.SuspensionRequest.requesting_user),
            joinedload(models.SuspensionRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).join(models.VacationPeriod).join(models.User).filter(
            models.User.area == user.area,
            models.SuspensionRequest.status == 'pending_review'
        ).all()

        data["finalized_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).join(models.User).filter(
            models.User.area == user.area,
            models.VacationPeriod.status.in_(['approved', 'rejected', 'suspended'])
        ).all()
        
        # --- NUEVO (FASE 3.2) ---
        data["upcoming_vacations"] = db.query(models.VacationPeriod).options(
            joinedload(models.VacationPeriod.user)
        ).join(models.User).filter(
            models.User.area == user.area,
            models.VacationPeriod.status == 'approved',
            models.VacationPeriod.start_date > today
        ).order_by(models.VacationPeriod.start_date).all()
        
    else:
        # Lógica de Empleado (sin cambios)
        data["my_vacations"] = db.query(models.VacationPeriod).filter(
            models.VacationPeriod.user_id == user.id
        ).order_by(models.VacationPeriod.start_date).all()
        
    return data
# --- FIN DE MODIFICACIÓN ---
# --- FIN DE MODIFICACIÓN ---

def get_vacation_by_id(db: Session, vacation_id: int):
    return db.query(models.VacationPeriod).options(
        joinedload(models.VacationPeriod.user)
    ).filter(models.VacationPeriod.id == vacation_id).first()

def update_vacation_status(db: Session, vacation: models.VacationPeriod, new_status: str, actor: models.User):
    if vacation:
        old_status = vacation.status
        vacation.status = new_status
        db.commit()
        db.refresh(vacation)
        
        create_vacation_log(db, vacation, actor, f"Estado cambiado de '{old_status}' a '{new_status}'.")
        
    return vacation

def check_edit_permission(vacation: models.VacationPeriod, user: models.User):
    if not vacation: return False
    if vacation.status != 'draft': return False
    if user.role in ['admin', 'hr']: return True
    if user.role == 'manager' and user.area == vacation.user.area: return True
    if user.role == 'employee' and user.id == vacation.user_id: return True
    return False

def update_vacation_details(
    db: Session,
    vacation: models.VacationPeriod,
    start_date_str: str,
    type_period: int,
    file_name: str,
    actor: models.User
):
    if not vacation:
        raise Exception("Solicitud no encontrada")
 
    user_balance = get_user_vacation_balance(db, vacation.user)
    available_balance = user_balance + vacation.days
    
    if type_period > available_balance:
        raise Exception("Error: No tienes suficientes días de balance para esta solicitud.")

    calculator = VacationCalculator(db)
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        calculation = calculator.calculate_end_date(sd, type_period)
        
        vacation.start_date = calculation["start_date"]
        vacation.end_date = calculation["end_date"]
        vacation.days = calculation["days_consumed"]
        vacation.type_period = type_period
        vacation.attached_file = file_name
        
        db.commit()
        db.refresh(vacation)
        
        create_vacation_log(db, vacation, actor, f"Solicitud editada. Nuevas fechas: {sd} por {type_period} días.")
        
        return vacation

    except ValueError as e:
        raise Exception(f"Error: {str(e)}")
    except Exception as e:
        raise Exception(f"Error inesperado: {str(e)}")

def submit_area_to_hr(db: Session, area: str, file_name: str, actor: models.User):
    vacations_to_update = db.query(models.VacationPeriod).join(models.User).filter(
        models.User.area == area,
        models.VacationPeriod.status == 'draft'
    ).all()

    if not vacations_to_update:
        return

    for v in vacations_to_update:
        v.status = "pending_hr"
        v.consolidated_doc_path = file_name
        create_vacation_log(db, v, actor, f"Enviado a RRHH con documento consolidado.")
    
    db.commit()

def submit_individual_to_hr(db: Session, vacation: models.VacationPeriod, actor: models.User, file_name: str):
    if vacation.status == 'draft':
        vacation.status = "pending_hr"
        vacation.manager_individual_doc_path = file_name # <-- AÑADIDO
        db.commit()
        create_vacation_log(db, vacation, actor, f"Enviado individualmente a RRHH (con sustento).")

def delete_vacation_period(db: Session, vacation_id: int):
    db_vacation = get_vacation_by_id(db, vacation_id)
    if db_vacation and db_vacation.status == 'draft':
        db.delete(db_vacation)
        db.commit()
    return db_vacation

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

def create_modification_request(
    db: Session, 
    vacation: models.VacationPeriod, 
    user: models.User, 
    reason: str, 
    file_name: str,
    new_start_date_str: str,
    new_period_type: int
):
    original_user = vacation.user
    user_balance = get_user_vacation_balance(db, original_user)
    available_balance = user_balance + vacation.days
    
    if new_period_type > available_balance:
        raise Exception("Error: El nuevo periodo excede el balance disponible.")

    calculator = VacationCalculator(db)
    try:
        sd = datetime.strptime(new_start_date_str, "%Y-%m-%d").date()
        calculation = calculator.calculate_end_date(sd, new_period_type)
    except ValueError as e:
        raise Exception(f"Error: {str(e)}")

    mod_req = models.ModificationRequest(
        vacation_period_id=vacation.id,
        requesting_user_id=user.id,
        reason_text=reason,
        attached_doc_path=file_name,
        status="pending_review",
        new_start_date=calculation["start_date"],
        new_end_date=calculation["end_date"],
        new_days=calculation["days_consumed"],
        new_period_type=new_period_type
    )
    db.add(mod_req)
    
    update_vacation_status(db, vacation, "pending_modification", user)
    
    db.commit()
    db.refresh(mod_req)
    
    create_vacation_log(db, vacation, user, f"Solicitó modificación. Propone: {sd} por {new_period_type} días. Motivo: {reason}")
    
    return mod_req

def get_modification_by_id(db: Session, mod_id: int):
    return db.query(models.ModificationRequest).filter(models.ModificationRequest.id == mod_id).first()

def approve_modification(db: Session, mod_id: int, actor: models.User):
    mod_req = get_modification_by_id(db, mod_id)
    if not mod_req or not mod_req.vacation_period:
        return None
        
    vacation = mod_req.vacation_period
    
    vacation.start_date = mod_req.new_start_date
    vacation.end_date = mod_req.new_end_date
    vacation.days = mod_req.new_days
    vacation.type_period = mod_req.new_period_type
    
    mod_req.status = "approved"
    vacation.status = "approved"
    
    create_vacation_log(db, vacation, actor, f"Modificación APROBADA. Nuevas fechas: {vacation.start_date} por {vacation.type_period} días.")
    
    db.commit()
    return mod_req

def reject_modification(db: Session, mod_id: int, actor: models.User):
    mod_req = get_modification_by_id(db, mod_id)
    if not mod_req:
        return None
        
    mod_req.status = "rejected"
    vacation = mod_req.vacation_period
    vacation.status = "rejected"
    
    create_vacation_log(db, vacation, actor, f"Modificación RECHAZADA.")
    
    db.commit()
    return mod_req

# --- NUEVAS FUNCIONES CRUD (PARTE 10) ---

def create_suspension_request(
    db: Session,
    vacation: models.VacationPeriod,
    actor: models.User,
    suspension_type: str,
    reason: str,
    file_name: str,
    new_end_date_str: str = None
):
    """Crea la solicitud de suspensión y actualiza el estado de la vacación original."""
    
    new_end_date = None
    if suspension_type == 'parcial':
        if not new_end_date_str:
            raise ValueError("Para suspensión parcial, 'new_end_date' es requerido.")
        new_end_date = datetime.strptime(new_end_date_str, "%Y-%m-%d").date()
        if new_end_date < vacation.start_date or new_end_date > vacation.end_date:
            raise ValueError("La nueva fecha de fin debe estar dentro del periodo original.")
    
    sus_req = models.SuspensionRequest(
        vacation_period_id=vacation.id,
        requesting_user_id=actor.id,
        suspension_type=suspension_type,
        reason_text=reason,
        attached_doc_path=file_name,
        new_end_date_parcial=new_end_date,
        status="pending_review"
    )
    db.add(sus_req)
    
    # Poner la vacación original en 'pending_suspension'
    update_vacation_status(db, vacation, "pending_suspension", actor)
    
    db.commit()
    db.refresh(sus_req)
    
    log_msg = f"Solicitó suspensión '{suspension_type}'. Motivo: {reason}"
    if new_end_date:
        log_msg += f" Nuevo fin: {new_end_date}"
    create_vacation_log(db, vacation, actor, log_msg)
    
    return sus_req

def get_suspension_by_id(db: Session, sus_id: int):
    """Obtiene una solicitud de suspensión por su ID."""
    return db.query(models.SuspensionRequest).options(
        joinedload(models.SuspensionRequest.vacation_period)
    ).filter(models.SuspensionRequest.id == sus_id).first()

def approve_suspension(db: Session, sus_id: int, actor: models.User):
    """
    Aprueba la suspensión:
    - total: marca la vacación original como 'suspended'.
    - parcial: recalcula los días/fecha de fin de la vacación original.
    """
    sus_req = get_suspension_by_id(db, sus_id)
    if not sus_req or not sus_req.vacation_period:
        return None
        
    vacation = sus_req.vacation_period
    
    if sus_req.suspension_type == 'total':
        vacation.status = 'suspended'
        log_msg = f"Suspensión TOTAL aprobada."
        
    elif sus_req.suspension_type == 'parcial':
        new_end_date = sus_req.new_end_date_parcial
        
        # Recalcular días gozados. (Simplificado: días calendario)
        # Una lógica más robusta usaría el 'VacationCalculator'
        days_consumed = (new_end_date - vacation.start_date).days + 1
        
        vacation.end_date = new_end_date
        vacation.days = days_consumed
        vacation.status = 'approved' # Sigue aprobada, pero con menos días
        log_msg = f"Suspensión PARCIAL aprobada. Nueva fecha de fin: {new_end_date}, Días gozados: {days_consumed}."
    
    sus_req.status = "approved"
    create_vacation_log(db, vacation, actor, log_msg)
    
    db.commit()
    return sus_req

def reject_suspension(db: Session, sus_id: int, actor: models.User):
    """
    Rechaza la suspensión:
    1. Marca la solicitud como 'rejected'.
    2. Devuelve la vacación original a 'approved'.
    """
    sus_req = get_suspension_by_id(db, sus_id)
    if not sus_req:
        return None
        
    sus_req.status = "rejected"
    vacation = sus_req.vacation_period
    vacation.status = "approved" # Vuelve a estar aprobada
    
    create_vacation_log(db, vacation, actor, f"Solicitud de suspensión RECHAZADA.")
    
    db.commit()
    return sus_req


# ... (después de change_user_password)

# --- AÑADIR NUEVAS FUNCIONES (FASE 5) ---

def get_user_by_id(db: Session, user_id: int):
    """Obtiene un usuario por su ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_all_users(db: Session):
    """Obtiene todos los usuarios, con sus managers cargados."""
    return db.query(models.User).options(
        joinedload(models.User.manager)
    ).order_by(models.User.username).all()

def get_all_managers(db: Session):
    """Obtiene todos los usuarios que son 'manager' o 'admin' o 'hr'."""
    return db.query(models.User).filter(
        models.User.role.in_(['manager', 'admin', 'hr'])
    ).order_by(models.User.username).all()

def admin_update_user(
    db: Session, 
    user: models.User, 
    username: str, 
    full_name: str, 
    email: str, 
    role: str, 
    area: str, 
    vacation_days_total: int, 
    manager_id: int
):
    """Actualiza los detalles de un usuario desde el panel de admin."""
    user.username = username
    user.full_name = full_name
    user.email = email
    user.role = role
    user.area = area
    user.vacation_days_total = vacation_days_total
    user.manager_id = manager_id if manager_id else None
    
    db.commit()
    db.refresh(user)
    return user



# --- FIN DE NUEVAS FUNCIONES ---