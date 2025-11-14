
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
    type_period = Column(Integer, nullable=False) # 30/15/7/8
    status = Column(String(30), default="draft")
    attached_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")
