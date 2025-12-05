# app/logic/vacation_calculator.py
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app import crud, models

class VacationCalculator:
    def __init__(self, db: Session, user: models.User = None):
        self.db = db
        self.user = user
        self.settings = self.load_settings()
        location = user.location if user else "CUSCO"
        self.holidays = self.load_holidays(location)

    def load_settings(self):
        settings_db = crud.get_all_settings(self.db)
        settings_dict = {s.key: s.value for s in settings_db}
        
        return {
            "HOLIDAYS_COUNT": settings_dict.get("HOLIDAYS_COUNT", "True") == "True",
            "FRIDAY_EXTENDS": settings_dict.get("FRIDAY_EXTENDS", "True") == "True",
            "ALLOW_START_ON_HOLIDAY": settings_dict.get("ALLOW_START_ON_HOLIDAY", "False") == "True",
            "ALLOW_START_ON_WEEKEND": settings_dict.get("ALLOW_START_ON_WEEKEND", "False") == "True",
        }

    def load_holidays(self, location: str):
        current_year = date.today().year
        holidays_this_year = crud.get_holidays_by_year(self.db, current_year, location)
        holidays_next_year = crud.get_holidays_by_year(self.db, current_year + 1, location)
        return {h.holiday_date for h in holidays_this_year + holidays_next_year}

    def is_weekend(self, day: date):
        return day.weekday() >= 5

    def is_holiday(self, day: date):
        return day in self.holidays

    def validate_start_date(self, start_date: date):

        if start_date <= date.today():
            return False, "La fecha de inicio debe ser posterior al día de hoy."
            
        if not self.settings["ALLOW_START_ON_WEEKEND"] and self.is_weekend(start_date):
            return False, "No se puede iniciar vacaciones en fin de semana."
        
        if not self.settings["ALLOW_START_ON_HOLIDAY"] and self.is_holiday(start_date):
            return False, "No se puede iniciar vacaciones en un día feriado."
        return True, None

    def validate_policy_dates(self, user: models.User, start_date: date):
        if not user.vacation_policy:
            return True, None
            
        policy = user.vacation_policy
        try:
            allowed_months = [int(m) for m in policy.allowed_months.split(",")]
        except ValueError:
            return True, None

        if start_date.month not in allowed_months:
            month_names = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            allowed_names = ", ".join([month_names[m] for m in allowed_months if 0 < m <= 12])
            return False, f"Según tu régimen, solo puedes iniciar en: {allowed_names}."
        
        return True, None

    def calculate_end_date(self, start_date: date, period_type: int):
        """
        Calcula fecha fin y COBRA los días extra si se extiende.
        """
        
        # 1. Validar Periodos Permitidos
        if period_type not in [7, 8, 15, 30]:
            raise ValueError("El periodo base debe ser de 7, 8, 15 o 30 días.")

        end_date = start_date + timedelta(days=period_type - 1)
        days_consumed = period_type
        messages = []

        # 2. Regla: Terminó en Viernes -> Extiende y COBRA
        if self.settings["FRIDAY_EXTENDS"] and end_date.weekday() == 4:
            # Extendemos 2 días (Sábado y Domingo) para que regrese el Lunes
            end_date = end_date + timedelta(days=2)
            days_consumed += 2 # <--- AHORA SÍ DESCUENTA LOS DÍAS
            
            messages.append(f"Aviso: Al terminar en viernes, se extiende al domingo. Se descontarán {days_consumed} días en total (Periodo Irregular).")

        # 3. Regla: Puente Prohibido (Terminar antes de feriado)
        next_day = end_date + timedelta(days=1)
        if next_day in self.holidays:
            raise ValueError(f"No se permite terminar el {end_date} porque el día siguiente es feriado (Puente prohibido).")

        return {
            "start_date": start_date,
            "end_date": end_date,
            "days_consumed": days_consumed,
            "messages": messages
        }
    def check_overlap(self, start_date: date, end_date: date):
        """Verifica si ya existen vacaciones en el rango seleccionado."""
        if not self.user:
            return True, None # Si no hay usuario, no podemos validar overlaps

        # Buscamos cualquier vacación que NO esté rechazada y que se cruce
        # Lógica de cruce: (InicioA <= FinB) y (FinA >= InicioB)
        overlap = self.db.query(models.VacationPeriod).filter(
            models.VacationPeriod.user_id == self.user.id,
            models.VacationPeriod.status.in_(['draft', 'pending_hr', 'approved', 'pending_modification']),
            models.VacationPeriod.start_date <= end_date,
            models.VacationPeriod.end_date >= start_date
        ).first()
        
        if overlap:
            return False, f"Cruce de fechas: Ya tienes una solicitud ({overlap.status}) del {overlap.start_date} al {overlap.end_date}."
            
        return True, None