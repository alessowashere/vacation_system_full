# app/logic/vacation_calculator.py
# (VERSIÓN CON RESTRICCIÓN DE MESES)

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
        settings_dict = {s.key: s.value for s in settings_db}
        
        return {
            "HOLIDAYS_COUNT": settings_dict.get("HOLIDAYS_COUNT", "True") == "True",
            "FRIDAY_EXTENDS": settings_dict.get("FRIDAY_EXTENDS", "True") == "True",
            "ALLOW_START_ON_HOLIDAY": settings_dict.get("ALLOW_START_ON_HOLIDAY", "False") == "True",
            "ALLOW_START_ON_WEEKEND": settings_dict.get("ALLOW_START_ON_WEEKEND", "False") == "True",
        }

    def load_holidays(self):
        current_year = date.today().year
        holidays_this_year = crud.get_holidays_by_year(self.db, current_year)
        holidays_next_year = crud.get_holidays_by_year(self.db, current_year + 1)
        return {h.holiday_date for h in holidays_this_year + holidays_next_year}

    def is_weekend(self, day: date):
        return day.weekday() >= 5

    def is_holiday(self, day: date):
        return day in self.holidays

    def is_non_working_day(self, day: date, count_holidays_as_vacation: bool):
        if self.is_weekend(day):
            return True
        if count_holidays_as_vacation:
            return False
        if self.is_holiday(day):
            return True
        return False

    def validate_start_date(self, start_date: date):
        if not self.settings["ALLOW_START_ON_WEEKEND"]:
            if self.is_weekend(start_date):
                return False
        
        if not self.settings["ALLOW_START_ON_HOLIDAY"]:
            if self.is_holiday(start_date):
                return False
        return True

    # app/logic/vacation_calculator.py
# (ACTUALIZAR EL MÉTODO validate_policy_dates)

    def validate_policy_dates(self, user: models.User, start_date: date):
            """Valida meses permitidos según la POLÍTICA asignada al usuario."""
            
            # Si el usuario no tiene política asignada, no hay restricción.
            if not user.vacation_policy:
                return True, None
                
            policy = user.vacation_policy
            allowed_months = [int(m) for m in policy.allowed_months.split(",")]
            
            if start_date.month not in allowed_months:
                month_names = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                allowed_names = ", ".join([month_names[m] for m in allowed_months])
                return False, f"Según tu régimen '{policy.name}', solo puedes iniciar vacaciones en: {allowed_names}."
            
            return True, None

    def calculate_end_date(self, start_date: date, period_type: int):
        # 1. Validación básica (fin de semana/feriado)
        if not self.validate_start_date(start_date):
            raise ValueError("La fecha de inicio no es válida (es fin de semana o feriado).")

        # (NOTA: La validación de políticas por usuario se debe llamar ANTES de usar esta función
        # o se puede integrar aquí pasando el usuario, pero para mantener la firma simple
        # lo dejaremos como un paso previo en el router).

        end_date = start_date + timedelta(days=period_type - 1)
        days_consumed = period_type
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "days_consumed": days_consumed
        }