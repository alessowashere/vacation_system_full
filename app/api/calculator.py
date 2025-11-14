# app/api/calculator.py
# (Archivo nuevo)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session

from app import crud, models
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

@router.post("/calculate-end-date", name="api_calculate_end_date")
def calculate_end_date_api(
    calc_request: DateCalculationRequest,
    current=Depends(get_current_user), # Protegido
    db: Session = Depends(get_db)
):
    """
    Toma una fecha de inicio y un tipo de periodo, y devuelve
    la fecha de fin calculada y cualquier advertencia.
    """
    calculator = VacationCalculator(db)
    
    try:
        # 1. Validar la fecha de inicio primero
        if not calculator.validate_start_date(calc_request.start_date):
            raise ValueError("La fecha de inicio no es válida (es fin de semana o feriado).")

        # 2. Si es válida, calcular el periodo
        calculation = calculator.calculate_end_date(
            calc_request.start_date, 
            calc_request.period_type
        )
        
        end_date = calculation["end_date"]
        warning_message = None

        # 3. Añadir advertencias
        if calculator.settings["FRIDAY_EXTENDS"] and end_date.weekday() == 6: # Es domingo
             warning_message = f"Observación: El periodo termina en viernes, por lo que se extiende hasta el {end_date} (Domingo)."
        
        return {
            "success": True,
            "end_date": end_date.strftime("%Y-%m-%d"),
            "warning": warning_message
        }

    except ValueError as e:
        # Si la fecha de inicio es inválida
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Cualquier otro error
        return {"success": False, "error": f"Error inesperado: {str(e)}"}