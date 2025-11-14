# app/models.py
# (VERSIÓN PARTE 6)

from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import relationship
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

    consolidated_doc_path = Column(String(255), nullable=True) # Documento del Jefe

class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

# --- NUEVO MODELO (PARTE 6) ---
class ModificationRequest(Base):
    """
    Almacena una solicitud de modificación de una vacación rechazada.
    """
    __tablename__ = "modification_requests"
    id = Column(Integer, primary_key=True, index=True)
    
    # La vacación original que fue rechazada
    vacation_period_id = Column(Integer, ForeignKey("vacation_periods.id"))
    vacation_period = relationship("VacationPeriod")
    
    # El 'boss' que solicita el cambio
    requesting_user_id = Column(Integer, ForeignKey("users.id"))
    requesting_user = relationship("User")
    
    reason_text = Column(Text, nullable=False)
    attached_doc_path = Column(String(255), nullable=False)
    status = Column(String(30), default="pending_review") # pending_review, approved, rejected
    created_at = Column(DateTime, default=datetime.utcnow)