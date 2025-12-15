# app/api/calculator.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_current_user
from app.db import SessionLocal
from app.logic.vacation_calculator import VacationCalculator

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DateCalculationRequest(BaseModel):
    start_date: date
    period_type: int
    target_user_id: int = None
    vacation_id: int = None  # <--- NUEVO CAMPO OPCIONAL

@router.post("/calculate-end-date", name="api_calculate_end_date")
def calculate_end_date_api(
    calc_request: DateCalculationRequest,
    current=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # Determinar usuario objetivo (si es un jefe asignando a otro)
    target_user = current
    if calc_request.target_user_id:
        found = crud.get_user_by_id(db, calc_request.target_user_id)
        if found: target_user = found
            
    calculator = VacationCalculator(db, target_user)

    try:
        # 1. Validar Fecha Inicio (Fin de semana / Feriado)
        valid_start, msg_start = calculator.validate_start_date(calc_request.start_date)
        if not valid_start:
            return {"success": False, "error": msg_start}

        # 2. Validar Políticas (Meses permitidos)
        valid_policy, msg_policy = calculator.validate_policy_dates(target_user, calc_request.start_date)
        if not valid_policy:
            return {"success": False, "error": msg_policy}
            
        valid_limit, msg_limit = calculator.check_period_type_limit(
            calc_request.start_date, 
            calc_request.period_type,
            ignore_vacation_id=calc_request.vacation_id
        )
        if not valid_limit:
            return {"success": False, "error": msg_limit}
            
        # 3. Calcular Fin y aplicar reglas de negocio (Viernes, Puentes, Periodos válidos)
        calculation = calculator.calculate_end_date(
            calc_request.start_date, 
            calc_request.period_type
        )
        
        # --- NUEVO: Validar Overlap ---
        valid_overlap, msg_overlap = calculator.check_overlap(
            calculation["start_date"], 
            calculation["end_date"],
            ignore_vacation_id=calc_request.vacation_id # <--- PASAMOS EL ID
        )
        
        if not valid_overlap:
            # Si hay cruce, devolvemos error (Rojo en el modal)
            return {"success": False, "error": msg_overlap}
        
        end_date = calculation["end_date"]
        msgs = calculation.get("messages", [])
        
        # Unir mensajes de advertencia/beneficio
        warning_text = " / ".join(calculation.get("messages", [])) if calculation.get("messages") else None
        
        return {
            "success": True,
            "end_date": calculation["end_date"].strftime("%Y-%m-%d"),
            "warning": warning_text
        }

    except ValueError as e:
        # Errores de validación de negocio (ej. terminar antes de feriado)
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error inesperado: {str(e)}"}