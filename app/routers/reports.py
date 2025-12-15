# app/routers/reports.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, date
import pandas as pd
import io

from app import crud, models
from app.db import get_db
from app.auth import get_current_admin_user

router = APIRouter(
    prefix="/gestion/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin_user)]
)

templates = Jinja2Templates(directory="app/templates")

# --- FUNCIONES AUXILIARES ---

def get_eligible_users_query(db: Session):
    """
    Retorna usuarios elegibles: Empleados y Managers con permiso activado.
    CORRECCIÓN: Se eliminó el filtro 'is_active' que causaba error.
    """
    return db.query(models.User).filter(
        # models.User.is_active == True,  <-- ELIMINADO
        or_(
            models.User.role == 'employee',
            and_(
                models.User.role == 'manager',
                models.User.can_request_own_vacation == True
            )
        )
    ).order_by(models.User.area, models.User.full_name)

# --- VISTA PRINCIPAL CON ALERTAS ---

@router.get("/", response_class=HTMLResponse, name="admin_reports_panel")
def reports_panel(request: Request, db: Session = Depends(get_db)):
    """
    Panel principal de reportes.
    """
    users_orm = get_eligible_users_query(db).all()
    
    users_view = []
    missing_schedule_alerts = []

    for u in users_orm:
        balance = crud.get_user_vacation_balance(db, u)
        taken = u.vacation_days_total - balance
        
        user_data = {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "can_request_own_vacation": u.can_request_own_vacation,
            "vacation_days_total": u.vacation_days_total,
            "vacation_days_taken": taken,
            "balance": balance
        }
        users_view.append(user_data)

        if balance > 10:
            missing_schedule_alerts.append(user_data)
            
    # Alerta: Jefes con solicitudes en borrador (draft)
    pending_periods = db.query(models.VacationPeriod).filter(
        models.VacationPeriod.status == 'draft'
    ).all()
    
    managers_ids_with_issues = set()
    for vp in pending_periods:
        if vp.user.manager_id:
            managers_ids_with_issues.add(vp.user.manager_id)
            
    managers_pending_objs = db.query(models.User).filter(
        models.User.id.in_(managers_ids_with_issues)
    ).all()

    alerts = {
        "missing_schedule": missing_schedule_alerts,
        "managers_pending": managers_pending_objs,
        "total_alerts": len(missing_schedule_alerts) + len(managers_pending_objs)
    }

    return templates.TemplateResponse("admin_reports.html", {
        "request": request,
        "users": users_view,
        "alerts": alerts
    })

# --- REPORTES DESCARGABLES ---

@router.get("/download/planned", name="report_planned")
def download_planned(db: Session = Depends(get_db)):
    today = date.today()
    eligible_users = get_eligible_users_query(db).all()
    eligible_ids = [u.id for u in eligible_users]

    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.user_id.in_(eligible_ids),
        models.VacationPeriod.start_date >= today,
        models.VacationPeriod.status.in_(['approved', 'pending_hr', 'pending_modification'])
    ).order_by(models.User.area.asc(), models.VacationPeriod.start_date.asc()).all()
    
    data = []
    for v in vacations:
        estado_esp = {
            "approved": "Aprobado", "pending_hr": "Pendiente RRHH",
            "pending_modification": "Solicita Cambio"
        }.get(v.status, v.status)

        data.append({
            "Área": v.user.area or "Sin Área",
            "Empleado": v.user.full_name,
            "DNI": v.user.username,
            "Inicio": v.start_date, "Fin": v.end_date, "Días": v.days,
            "Estado": estado_esp,
            "Jefe": v.user.manager.full_name if v.user.manager else "Sin Jefe"
        })
    
    return generate_excel_response(data, "Planificacion_Filtrada")

@router.get("/download/history", name="report_history")
def download_history(db: Session = Depends(get_db)):
    eligible_users = get_eligible_users_query(db).all()
    eligible_ids = [u.id for u in eligible_users]

    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.user_id.in_(eligible_ids)
    ).order_by(models.VacationPeriod.created_at.desc()).all()
    
    data = []
    for v in vacations:
        data.append({
            "ID": v.id, "Empleado": v.user.full_name, "Área": v.user.area,
            "Inicio": v.start_date, "Fin": v.end_date, "Días": v.days,
            "Estado": v.status, "Solicitado": v.created_at.strftime("%Y-%m-%d")
        })
    return generate_excel_response(data, "Historial_Global")

@router.get("/download/balances", name="report_balances")
def download_balances(db: Session = Depends(get_db)):
    users = get_eligible_users_query(db).all()
    data = []
    for u in users:
        balance = crud.get_user_vacation_balance(db, u)
        data.append({
            "DNI": u.username, "Nombre": u.full_name, "Área": u.area,
            "Rol": u.role, "Auto-Solicitud": "SÍ" if u.can_request_own_vacation else "NO",
            "Total": u.vacation_days_total, "Saldo": balance
        })
    return generate_excel_response(data, "Reporte_Saldos")

def generate_excel_response(data: list, file_prefix: str):
    if not data: df = pd.DataFrame([{"Mensaje": "No hay datos"}])
    else: df = pd.DataFrame(data)
        
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Datos")
        for idx, col in enumerate(df.columns):
            writer.sheets["Datos"].column_dimensions[chr(65 + idx)].width = 20
            
    stream.seek(0)
    filename = f"{file_prefix}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )