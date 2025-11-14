
from .db import SessionLocal
from . import models
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

def create_vacation(user, start_date_str, type_period, file_path=None):
    db = SessionLocal()
    sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    # compute end date based on rules (count calendar days, extend if ends on Friday)
    end = sd + timedelta(days=type_period-1)
    if end.weekday() == 4: # friday
        end = end + timedelta(days=2)
    days = (end - sd).days + 1
    vp = models.VacationPeriod(user_id=user.id, start_date=sd, end_date=end, days=days, type_period=type_period, attached_file=file_path)
    db.add(vp); db.commit(); db.refresh(vp); db.close()
    return vp

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
