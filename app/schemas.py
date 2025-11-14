
from pydantic import BaseModel
from datetime import date
from typing import Optional

class UserBase(BaseModel):
    username: str
    full_name: Optional[str]
    email: Optional[str]
    role: Optional[str] = "employee"

class UserCreate(UserBase):
    password: str

class VacationCreate(BaseModel):
    start_date: date
    type_period: int
