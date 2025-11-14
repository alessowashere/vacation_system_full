# app/schemas.py
# (VERSIÓN CORREGIDA PARTE 3)

from pydantic import BaseModel
from datetime import date
from typing import Optional

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None # Corregido
    email: Optional[str] = None # Corregido
    role: Optional[str] = "employee"

class UserCreate(UserBase):
    password: str

class VacationCreate(BaseModel):
    start_date: date
    type_period: int

# --- ESQUEMAS DE FERIADOS (DE PARTE 1) ---

class HolidayBase(BaseModel):
    holiday_date: date
    name: str
    is_national: Optional[bool] = True

class HolidayCreate(HolidayBase):
    pass

class Holiday(HolidayBase):
    id: int

    class Config:
        from_attributes = True # <-- CORREGIDO DE 'orm_mode'