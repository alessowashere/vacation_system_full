# app/models.py
# (VERSIÓN PARTE 10)

from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import relationship, backref # <-- AÑADIR backref
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(120))
    email = Column(String(120))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="employee")
    area = Column(String(120), nullable=True)
    force_password_change = Column(Boolean, default=True)

    # --- AÑADIR ESTAS LÍNEAS (FASE 5) ---
    vacation_days_total = Column(Integer, default=30)
    
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    manager = relationship("User", remote_side=[id], backref="subordinates")
    # --- FIN DE LÍNEAS A AÑADIR ---

    created_at = Column(DateTime, default=datetime.utcnow)

class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    holiday_date = Column(Date, nullable=False, unique=True)
    name = Column(String(200))
    is_national = Column(Boolean, default=True)

class VacationPeriod(Base):
    __tablename__ = "vacation_periods"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, nullable=False)
    type_period = Column(Integer, nullable=False)
    status = Column(String(30), default="draft")
    attached_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")

    consolidated_doc_path = Column(String(255), nullable=True)
    manager_individual_doc_path = Column(String(255), nullable=True)

class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

class ModificationRequest(Base):
    __tablename__ = "modification_requests"
    id = Column(Integer, primary_key=True, index=True)
    
    vacation_period_id = Column(Integer, ForeignKey("vacation_periods.id"))
    vacation_period = relationship("VacationPeriod")
    
    requesting_user_id = Column(Integer, ForeignKey("users.id"))
    requesting_user = relationship("User")
    
    reason_text = Column(Text, nullable=False)
    attached_doc_path = Column(String(255), nullable=False)
    status = Column(String(30), default="pending_review") 
    created_at = Column(DateTime, default=datetime.utcnow)

    new_start_date = Column(Date, nullable=True)
    new_period_type = Column(Integer, nullable=True)
    new_end_date = Column(Date, nullable=True)
    new_days = Column(Integer, nullable=True)

class VacationLog(Base):
    __tablename__ = "vacation_logs"
    id = Column(Integer, primary_key=True, index=True)
    
    vacation_period_id = Column(Integer, ForeignKey("vacation_periods.id"))
    vacation_period = relationship("VacationPeriod")
    
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User")
    
    log_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- NUEVO MODELO (PARTE 10) ---
class SuspensionRequest(Base):
    """
    Almacena una solicitud de suspensión de una vacación APROBADA.
    """
    __tablename__ = "suspension_requests"
    id = Column(Integer, primary_key=True, index=True)
    
    vacation_period_id = Column(Integer, ForeignKey("vacation_periods.id"))
    vacation_period = relationship("VacationPeriod")
    
    requesting_user_id = Column(Integer, ForeignKey("users.id"))
    requesting_user = relationship("User")
    
    suspension_type = Column(String(20), nullable=False) # "total" o "parcial"
    reason_text = Column(Text, nullable=False)
    attached_doc_path = Column(String(255), nullable=False)
    status = Column(String(30), default="pending_review")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Solo para suspensiones parciales
    new_end_date_parcial = Column(Date, nullable=True)