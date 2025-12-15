# app/crud.py
import re
from .db import SessionLocal, get_db
from . import models
from sqlalchemy import func, and_, or_
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import os
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any

from app.logic.vacation_calculator import VacationCalculator

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def get_user_by_username(db, username):
    return db.query(models.User).filter(models.User.username==username).first()

def create_user(
    username, 
    role="employee", 
    full_name=None, 
    email=None, 
    area=None, 
    vacation_days_total=30, 
    manager_id=None,
    location="CUSCO",
    can_request_own_vacation=False
):
    db = SessionLocal()
    u = models.User(
        username=username, 
        role=role, 
        full_name=full_name, 
        email=email, 
        area=area,
        vacation_days_total=vacation_days_total,
        manager_id=manager_id,
        location=location,
        can_request_own_vacation=can_request_own_vacation
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u

def get_user_vacation_balance(db: Session, user: models.User):
    total_days_used = db.query(func.sum(models.VacationPeriod.days)).filter(
        models.VacationPeriod.user_id == user.id,
        models.VacationPeriod.status.in_(['draft', 'pending_hr', 'approved', 'pending_modification', 'pending_suspension'])
    ).scalar()
    
    if total_days_used is None:
        total_days_used = 0
        
    return user.vacation_days_total - total_days_used

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
        raise ValueError(f"Saldo insuficiente ({remaining_balance} días). No puedes pedir {type_period}.")
    
    calculator = VacationCalculator(db, user)
    
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        
        is_valid_limit, limit_msg = calculator.check_period_type_limit(sd, type_period)
        if not is_valid_limit:
            raise ValueError(limit_msg)
            
        is_valid_date, date_msg = calculator.validate_start_date(sd)
        if not is_valid_date:
            raise ValueError(date_msg)

        calculation = calculator.calculate_end_date(sd, type_period)
        final_start = calculation["start_date"]
        final_end = calculation["end_date"]
        real_days = calculation["days_consumed"]

        is_valid_overlap, error_overlap = calculator.check_overlap(final_start, final_end)
        if not is_valid_overlap:
            raise ValueError(error_overlap)

        if real_days > remaining_balance:
             raise ValueError(f"Saldo insuficiente. La solicitud requiere {real_days} días (incluye extensiones), tienes {remaining_balance}.")

        vp = models.VacationPeriod(
            user_id=user.id,
            start_date=final_start,
            end_date=final_end,
            days=real_days,
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

def get_dashboard_data(db: Session, user: models.User):
    data = {}
    today = date.today()
    
    base_query = db.query(models.VacationPeriod).options(joinedload(models.VacationPeriod.user))
    
    if user.role == "manager":
        conditions = [models.User.manager_id == user.id]
        if user.can_request_own_vacation:
            conditions.append(models.User.id == user.id)
        base_query = base_query.join(models.User).filter(or_(*conditions))
    elif user.role == "employee":
        base_query = base_query.filter(models.VacationPeriod.user_id == user.id)

    data["draft_vacations"] = base_query.filter(models.VacationPeriod.status == 'draft').all()
    data["pending_vacations"] = base_query.filter(models.VacationPeriod.status == 'pending_hr').all()
    
    if user.role == "manager":
        data["pending_modifications"] = db.query(models.ModificationRequest).options(
            joinedload(models.ModificationRequest.requesting_user),
            joinedload(models.ModificationRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).join(models.VacationPeriod).join(models.User).filter(
            models.User.manager_id == user.id,
            models.ModificationRequest.status == 'pending_review'
        ).all()
        
        data["pending_suspensions"] = db.query(models.SuspensionRequest).options(
            joinedload(models.SuspensionRequest.requesting_user),
            joinedload(models.SuspensionRequest.vacation_period).joinedload(models.VacationPeriod.user)
        ).join(models.VacationPeriod).join(models.User).filter(
            models.User.manager_id == user.id,
            models.SuspensionRequest.status == 'pending_review'
        ).all()
    elif user.role in ["admin", "hr"]:
        data["pending_modifications"] = db.query(models.ModificationRequest).filter(
            models.ModificationRequest.status == 'pending_review'
        ).all()
        data["pending_suspensions"] = db.query(models.SuspensionRequest).filter(
            models.SuspensionRequest.status == 'pending_review'
        ).all()
    else:
        data["pending_modifications"] = []
        data["pending_suspensions"] = []

    data["upcoming_vacations"] = base_query.filter(
        models.VacationPeriod.status == 'approved',
        models.VacationPeriod.start_date >= today
    ).order_by(models.VacationPeriod.start_date).all()

    data["finalized_vacations"] = base_query.filter(
        (models.VacationPeriod.status.in_(['rejected', 'suspended'])) | 
        (
            (models.VacationPeriod.status == 'approved') & 
            (models.VacationPeriod.start_date < today)
        )
    ).order_by(models.VacationPeriod.start_date.desc()).all()
    
    if user.role == "employee":
        data["my_vacations"] = base_query.order_by(models.VacationPeriod.start_date.desc()).all()
        
    return data

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
    if user.id == vacation.user_id: return True
    if user.role in ['admin', 'hr']: return True
    if user.role == 'manager' and vacation.user.manager_id == user.id: return True
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
 
    current_balance = get_user_vacation_balance(db, vacation.user)
    available_balance_for_edit = current_balance + vacation.days
    
    if type_period > available_balance_for_edit:
        raise Exception(f"Error: El periodo ({type_period}) excede tu saldo disponible para editar ({available_balance_for_edit}).")

    calculator = VacationCalculator(db, vacation.user)
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        
        is_valid_limit, limit_msg = calculator.check_period_type_limit(sd, type_period, ignore_vacation_id=vacation.id)
        if not is_valid_limit:
            raise ValueError(limit_msg)
        
        is_valid_date, date_msg = calculator.validate_start_date(sd)
        if not is_valid_date:
            raise ValueError(date_msg)

        calculation = calculator.calculate_end_date(sd, type_period)
        real_days = calculation["days_consumed"]
        
        if real_days > available_balance_for_edit:
             raise ValueError(f"Saldo insuficiente. Requieres {real_days} días, tienes {available_balance_for_edit}.")

        vacation.start_date = calculation["start_date"]
        vacation.end_date = calculation["end_date"]
        vacation.days = real_days
        vacation.type_period = type_period
        if file_name:
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
        models.User.manager_id == actor.id,
        models.VacationPeriod.status == 'draft'
    ).all()

    if not vacations_to_update:
        return

    for v in vacations_to_update:
        v.status = "pending_hr"
        if file_name:
            v.consolidated_doc_path = file_name
        create_vacation_log(db, v, actor, f"Enviado a RRHH en lote por el jefe.")
    
    db.commit()

def submit_individual_to_hr(db: Session, vacation: models.VacationPeriod, actor: models.User, file_name: str):
    if vacation.status == 'draft':
        vacation.status = "pending_hr"
        vacation.manager_individual_doc_path = file_name
        db.commit()
        create_vacation_log(db, vacation, actor, f"Enviado individualmente a RRHH (con sustento).")

def delete_vacation_period(db: Session, vacation_id: int):
    db_vacation = get_vacation_by_id(db, vacation_id)
    if db_vacation and db_vacation.status == 'draft':
        db.query(models.VacationLog).filter(models.VacationLog.vacation_period_id == vacation_id).delete()
        db.query(models.ModificationRequest).filter(models.ModificationRequest.vacation_period_id == vacation_id).delete()
        db.query(models.SuspensionRequest).filter(models.SuspensionRequest.vacation_period_id == vacation_id).delete()
        db.delete(db_vacation)
        db.commit()
    return db_vacation

def get_holiday(db: Session, holiday_id: int):
    return db.query(models.Holiday).filter(models.Holiday.id == holiday_id).first()
def get_holiday_by_date(db: Session, holiday_date: date):
    return db.query(models.Holiday).filter(models.Holiday.holiday_date == holiday_date).first()

def get_holidays_by_year(db: Session, year: int, user_location: str = "CUSCO"):
    return db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= date(year, 1, 1),
        models.Holiday.holiday_date <= date(year, 12, 31),
        models.Holiday.location.in_(["GENERAL", user_location])
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
    pass 

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

def create_modification_request(db: Session, vacation: models.VacationPeriod, user: models.User, reason: str, file_name: str, new_start_date_str: str, new_period_type: int):
    original_user = vacation.user
    user_balance = get_user_vacation_balance(db, original_user)
    available_balance = user_balance + vacation.days
    
    if new_period_type > available_balance:
        raise Exception("Error: El nuevo periodo excede el balance disponible.")

    calculator = VacationCalculator(db, original_user)
    try:
        sd = datetime.strptime(new_start_date_str, "%Y-%m-%d").date()
        is_valid_date, date_msg = calculator.validate_start_date(sd)
        if not is_valid_date:
            raise ValueError(date_msg)

        calculation = calculator.calculate_end_date(sd, new_period_type)
        real_days = calculation["days_consumed"]

        if real_days > available_balance:
             raise ValueError(f"Saldo insuficiente. La modificación requiere {real_days} días, tienes {available_balance}.")

    except ValueError as e:
        raise Exception(f"Error: {str(e)}")

    mod_req = models.ModificationRequest(
        vacation_period_id=vacation.id,
        requesting_user_id=user.id,
        reason_text=reason,
        attached_doc_path=file_name,
        new_start_date=calculation["start_date"],
        new_end_date=calculation["end_date"],
        new_days=real_days,
        new_period_type=new_period_type,
        status="pending_review"
    )
    db.add(mod_req)
    update_vacation_status(db, vacation, "pending_modification", user)
    db.commit()
    db.refresh(mod_req)
    create_vacation_log(db, vacation, user, f"Solicitó modificación. Nueva fecha tentativa: {sd} ({new_period_type} días).")
    return mod_req

def get_modification_by_id(db: Session, mod_id: int):
    return db.query(models.ModificationRequest).filter(models.ModificationRequest.id == mod_id).first()

def approve_modification(db: Session, mod_id: int, actor: models.User):
    mod_req = get_modification_by_id(db, mod_id)
    if not mod_req or not mod_req.vacation_period: return None
        
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
    if not mod_req: return None
        
    mod_req.status = "rejected"
    vacation = mod_req.vacation_period
    vacation.status = "rejected"
    
    create_vacation_log(db, vacation, actor, f"Modificación RECHAZADA.")
    db.commit()
    return mod_req

def create_suspension_request(db: Session, vacation: models.VacationPeriod, actor: models.User, suspension_type: str, reason: str, file_name: str, new_end_date_str: str = None):
    new_end_date = None
    if suspension_type == 'parcial':
        if not new_end_date_str: raise ValueError("Para suspensión parcial, 'new_end_date' es requerido.")
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
    update_vacation_status(db, vacation, "pending_suspension", actor)
    db.commit()
    db.refresh(sus_req)
    
    log_msg = f"Solicitó suspensión '{suspension_type}'. Motivo: {reason}"
    if new_end_date: log_msg += f" Nuevo fin: {new_end_date}"
    create_vacation_log(db, vacation, actor, log_msg)
    return sus_req

def get_suspension_by_id(db: Session, sus_id: int):
    return db.query(models.SuspensionRequest).options(
        joinedload(models.SuspensionRequest.vacation_period)
    ).filter(models.SuspensionRequest.id == sus_id).first()

def approve_suspension(db: Session, sus_id: int, actor: models.User):
    sus_req = get_suspension_by_id(db, sus_id)
    if not sus_req or not sus_req.vacation_period: return None
        
    vacation = sus_req.vacation_period
    
    if sus_req.suspension_type == 'total':
        vacation.status = 'suspended'
        log_msg = f"Suspensión TOTAL aprobada."
    elif sus_req.suspension_type == 'parcial':
        new_end_date = sus_req.new_end_date_parcial
        days_consumed = (new_end_date - vacation.start_date).days + 1
        vacation.end_date = new_end_date
        vacation.days = days_consumed
        vacation.status = 'approved'
        log_msg = f"Suspensión PARCIAL aprobada. Nueva fecha de fin: {new_end_date}, Días gozados: {days_consumed}."
    
    sus_req.status = "approved"
    create_vacation_log(db, vacation, actor, log_msg)
    db.commit()
    return sus_req

def reject_suspension(db: Session, sus_id: int, actor: models.User):
    sus_req = get_suspension_by_id(db, sus_id)
    if not sus_req: return None
        
    sus_req.status = "rejected"
    vacation = sus_req.vacation_period
    vacation.status = "approved"
    
    create_vacation_log(db, vacation, actor, f"Solicitud de suspensión RECHAZADA.")
    db.commit()
    return sus_req

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_all_users(db: Session):
    return db.query(models.User).options(joinedload(models.User.manager)).order_by(models.User.username).all()

def get_all_managers(db: Session):
    return db.query(models.User).filter(models.User.role.in_(['manager', 'admin', 'hr'])).order_by(models.User.username).all()

def admin_update_user(db: Session, user: models.User, username: str, full_name: str, email: str, role: str, area: str, vacation_days_total: int, manager_id: int, vacation_policy_id: int = None, location: str = "CUSCO", can_request_own_vacation: bool = False): 
    user.username = username
    user.full_name = full_name
    user.email = email
    user.role = role
    user.area = area
    user.vacation_days_total = vacation_days_total
    user.manager_id = manager_id if manager_id else None
    user.vacation_policy_id = vacation_policy_id if vacation_policy_id else None
    user.location = location
    user.can_request_own_vacation = can_request_own_vacation
    db.commit()
    db.refresh(user)
    return user

def get_all_policies(db: Session):
    return db.query(models.VacationPolicy).all()

def create_policy(db: Session, name: str, months: List[int]):
    months_str = ",".join(map(str, months))
    policy = models.VacationPolicy(name=name, allowed_months=months_str)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy

def delete_policy(db: Session, policy_id: int):
    policy = db.query(models.VacationPolicy).filter(models.VacationPolicy.id == policy_id).first()
    if policy:
        db.delete(policy)
        db.commit()
    return policy

def get_users_by_manager(db: Session, manager_id: int):
    return db.query(models.User).filter(models.User.manager_id == manager_id).order_by(models.User.full_name).all()