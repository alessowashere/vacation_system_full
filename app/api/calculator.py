# app/api/calculator.py
# (VERSIÓN ACTUALIZADA)

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
    target_user_id: int = None # Opcional, para cuando un jefe calcula para otro

@router.post("/calculate-end-date", name="api_calculate_end_date")
def calculate_end_date_api(
    calc_request: DateCalculationRequest,
    current=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    calculator = VacationCalculator(db)
    
    # Determinar para qué usuario estamos calculando
    target_user = current
    if calc_request.target_user_id:
        # (Aquí podrías añadir validación de permisos si fuera crítico)
        found_user = crud.get_user_by_id(db, calc_request.target_user_id)
        if found_user:
            target_user = found_user

    try:
        # 1. Validar Reglas de Políticas (Meses permitidos)
        allowed, msg = calculator.validate_policy_dates(target_user, calc_request.start_date)
        if not allowed:
            return {"success": False, "error": msg}

        # 2. Validar Reglas de Calendario (Fines de semana/Feriados)
        if not calculator.validate_start_date(calc_request.start_date):
            raise ValueError("La fecha de inicio no es válida (es fin de semana o feriado).")

        # 3. Calcular
        calculation = calculator.calculate_end_date(
            calc_request.start_date, 
            calc_request.period_type
        )
        
        end_date = calculation["end_date"]
        warning_message = None

        if calculator.settings["FRIDAY_EXTENDS"] and end_date.weekday() == 6: 
             warning_message = f"Observación: El periodo termina en viernes, por lo que se extiende hasta el {end_date} (Domingo)."
        
        return {
            "success": True,
            "end_date": end_date.strftime("%Y-%m-%d"),
            "warning": warning_message
        }

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error inesperado: {str(e)}"}