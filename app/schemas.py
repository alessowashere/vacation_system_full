
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
# --- Añadir estas clases al final de app/schemas.py ---

from pydantic import BaseModel
from datetime import date
from typing import Optional

# ... (clases UserBase, UserCreate, VacationCreate existentes) ...

class HolidayBase(BaseModel):
    holiday_date: date
    name: str
    is_national: Optional[bool] = True

class HolidayCreate(HolidayBase):
    pass

class Holiday(HolidayBase):
    id: int

    class Config:
        orm_mode = True