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
    email = Column(String(120), unique=True, index=True) # <-- Hice el email único
    role = Column(String(20), default="employee")
    area = Column(String(120), nullable=True)
    vacation_days_total = Column(Integer, default=30)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    manager = relationship("User", remote_side=[id], backref="subordinates")
    created_at = Column(DateTime, default=datetime.utcnow)
    vacation_policy_id = Column(Integer, ForeignKey("vacation_policies.id"), nullable=True)
    vacation_policy = relationship("VacationPolicy")
    location = Column(String(50), default="CUSCO")
    can_request_own_vacation = Column(Boolean, default=False)

class VacationPolicy(Base):
    __tablename__ = "vacation_policies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False) # Ej: "Régimen Docente"
    allowed_months = Column(String(50), nullable=False) # Ej: "1,2,7"
    
class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    # ELIMINAR unique=True de holiday_date, porque dos sedes pueden tener feriado el mismo día con distinto nombre
    holiday_date = Column(Date, nullable=False) 
    name = Column(String(200))
    is_national = Column(Boolean, default=True)
    # NUEVA COLUMNA:
    location = Column(String(50), default="GENERAL")

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

# app/models.py
# (AÑADIR AL FINAL, ANTES DE LA ULTIMA LÍNEA)

class AreaRestriction(Base):
    __tablename__ = "area_restrictions"
    id = Column(Integer, primary_key=True, index=True)
    area_name = Column(String(100), unique=True, nullable=False) # Ej: "DOCENCIA", "SEGURIDAD"
    allowed_months = Column(String(50), nullable=False) # Ej: "1,2,7" (Enero, Febrero, Julio)