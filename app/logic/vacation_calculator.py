# app/logic/vacation_calculator.py
# (Archivo nuevo)

from sqlalchemy.orm import Session
from datetime import date, timedelta
from app import crud, models

class VacationCalculator:
    def __init__(self, db: Session):
        self.db = db
        self.settings = self.load_settings()
        self.holidays = self.load_holidays()

    def load_settings(self):
        """Carga las configuraciones del sistema desde la BD."""
        settings_db = crud.get_all_settings(self.db)
        # Convierte la lista de K/V en un diccionario útil
        settings_dict = {s.key: s.value for s in settings_db}
        
        # Valores por defecto si no están en la BD
        return {
            "HOLIDAYS_COUNT": settings_dict.get("HOLIDAYS_COUNT", "True") == "True",
            "FRIDAY_EXTENDS": settings_dict.get("FRIDAY_EXTENDS", "True") == "True",
            "ALLOW_START_ON_HOLIDAY": settings_dict.get("ALLOW_START_ON_HOLIDAY", "False") == "True",
            "ALLOW_START_ON_WEEKEND": settings_dict.get("ALLOW_START_ON_WEEKEND", "False") == "True",
        }

    def load_holidays(self):
        """Carga un set de fechas de feriados para búsquedas rápidas."""
        # Carga feriados de este año y el próximo, por si acaso
        current_year = date.today().year
        holidays_this_year = crud.get_holidays_by_year(self.db, current_year)
        holidays_next_year = crud.get_holidays_by_year(self.db, current_year + 1)
        
        # Devuelve un set de 'date' objects
        return {h.holiday_date for h in holidays_this_year + holidays_next_year}

    def is_weekend(self, day: date):
        """Verifica si es sábado (5) o domingo (6)."""
        return day.weekday() >= 5

    def is_holiday(self, day: date):
        """Verifica si la fecha está en nuestro set de feriados."""
        return day in self.holidays

    def is_non_working_day(self, day: date, count_holidays_as_vacation: bool):
        """
        Verifica si un día es fin de semana O feriado (si los feriados no cuentan).
        """
        if self.is_weekend(day):
            return True
        
        # Si la configuración dice que los feriados SÍ cuentan para vacaciones,
        # entonces NO se consideran "no laborables" para el cálculo.
        if count_holidays_as_vacation:
            return False
            
        # Si NO cuentan, entonces un feriado es un día no laborable.
        if self.is_holiday(day):
            return True
            
        return False

    def validate_start_date(self, start_date: date):
        """
        Valida la fecha de inicio según las reglas.
        Devuelve True si es válida, False si no.
        """
        if not self.settings["ALLOW_START_ON_WEEKEND"]:
            if self.is_weekend(start_date):
                return False
        
        if not self.settings["ALLOW_START_ON_HOLIDAY"]:
            if self.is_holiday(start_date):
                return False
                
        return True

    def calculate_end_date(self, start_date: date, period_type: int):
        """
        Calcula la fecha de fin y los días consumidos basándose en las reglas.
        """
        
        # 1. Validación de la fecha de inicio
        if not self.validate_start_date(start_date):
            raise ValueError("Invalid start date based on business rules.")

        # 2. Configuración de cálculo
        # ¿Los feriados cuentan contra el balance?
        count_holidays = self.settings["HOLIDAYS_COUNT"]
        
        current_date = start_date
        days_counted = 0
        
        # 3. Conteo de días
        # El bucle avanza día por día hasta consumir los 'period_type' días.
        while days_counted < period_type:
            
            # Si el día actual NO es fin de semana Y NO es un feriado (o los feriados cuentan)
            if not self.is_non_working_day(current_date, count_holidays):
                days_counted += 1
            
            # Si aún no hemos terminado, avanzamos al siguiente día
            if days_counted < period_type:
                current_date += timedelta(days=1)

        # 4. Ajuste de fin de semana (Regla "Viernes extiende")
        end_date = current_date
        if self.settings["FRIDAY_EXTENDS"] and end_date.weekday() == 4: # Es viernes
            end_date += timedelta(days=2) # Extiende a domingo
            
        # 5. Cálculo de días consumidos
        # Los días consumidos del balance son siempre el tipo de periodo (7, 8, 15, 30)
        # La regla de "extender viernes" no consume más días de balance (según diseño).
        days_consumed = period_type

        return {
            "start_date": start_date,
            "end_date": end_date,
            "days_consumed": days_consumed
        }