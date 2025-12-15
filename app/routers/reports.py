# app/routers/reports.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, date
import pandas as pd
import io

# Importaciones que deben existir en tu proyecto
from app import crud, models
from app.db import get_db
from app.auth import get_current_admin_user

# Configuración del router
router = APIRouter(
    prefix="/gestion/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin_user)] # Solo admins pueden ver esto
)

# Configuración de templates (Asegúrate de que la ruta sea correcta)
templates = Jinja2Templates(directory="app/templates")

# --- FUNCIONES AUXILIARES (Lógica interna) ---

def get_eligible_users_query(db: Session):
    """
    Retorna la query base de usuarios que pueden pedir vacaciones:
    - Todos los empleados (role='employee')
    - Managers con flag (role='manager' AND can_request_own_vacation=True)
    - Excluye Admins puros o Managers que no piden vacaciones.
    """
    return db.query(models.User).filter(
        # Filtro de Roles
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
    Panel principal de reportes con alertas y listado filtrado.
    """
    # 1. Obtener usuarios elegibles (para la tabla y cálculos)
    # Se asume que crud.get_user_vacation_balance existe y funciona
    users = get_eligible_users_query(db).all()
    
    # 2. Calcular Alertas
    
    # A) Alerta: Falta Programar (Saldo > 10 días)
    missing_schedule = []
    for u in users:
        # Nota: Asumo que crud.get_user_vacation_balance(db, u) es la forma de obtener el saldo.
        # Si no existe, tendrás que usar u.vacation_days_total - u.vacation_days_taken directamente si los campos están actualizados.
        try:
            balance = crud.get_user_vacation_balance(db, u)
        except AttributeError:
            # Fallback si no tienes crud.get_user_vacation_balance implementado
            balance = u.vacation_days_total - u.vacation_days_taken

        if balance > 10: # Umbral configurable
            missing_schedule.append({
                "user": u,
                "balance": balance
            })
            
    # B) Alerta: Jefes con solicitudes pendientes (Subordinados en 'draft' o 'pending')
    # Nota: He ajustado para que busque VacationPeriod en 'draft', 
    # asumiendo que es el estado inicial que debe ver el manager.
    draft_vacations = db.query(models.VacationPeriod).filter(
        models.VacationPeriod.status == 'draft' # O usa 'pending' si tu flujo es diferente
    ).all()
    
    managers_with_pending_ids = set()
    for v in draft_vacations:
        if v.user.manager_id:
            managers_with_pending_ids.add(v.user.manager_id)
            
    managers_pending = db.query(models.User).filter(
        models.User.id.in_(managers_with_pending_ids)
    ).all()

    alerts = {
        "missing_schedule": missing_schedule,
        "managers_pending": managers_pending,
        "total_alerts": len(missing_schedule) + len(managers_pending)
    }

    # Esta es la línea que resuelve el error UndefinedError,
    # asegurando que 'alerts' y 'users' se pasen al template
    return templates.TemplateResponse("admin_reports.html", {
        "request": request,
        "users": users,
        "alerts": alerts
    })

# --- REPORTE 1: PLANIFICADOS (Filtrado) ---
@router.get("/download/planned", name="report_planned")
def download_planned(db: Session = Depends(get_db)):
    """
    Descarga reporte de vacaciones FUTURAS para usuarios elegibles.
    """
    # ... (El resto del código de la función download_planned es el mismo)
    today = date.today()
    
    eligible_users = get_eligible_users_query(db).all()
    eligible_ids = [u.id for u in eligible_users]

    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.user_id.in_(eligible_ids),
        models.VacationPeriod.start_date >= today,
        models.VacationPeriod.status.in_(['approved', 'pending_hr', 'pending_modification'])
    ).order_by(
        models.User.area.asc(),
        models.VacationPeriod.start_date.asc()
    ).all()
    
    data = []
    for v in vacations:
        estado_esp = {
            "approved": "Aprobado",
            "pending_hr": "Pendiente RRHH",
            "pending_modification": "Solicita Cambio"
        }.get(v.status, v.status)

        data.append({
            "Área / Oficina": v.user.area or "Sin Área",
            "Empleado": v.user.full_name or v.user.username,
            "DNI/Usuario": v.user.username,
            "Fecha Inicio": v.start_date,
            "Fecha Fin": v.end_date,
            "Días": v.days,
            "Estado": estado_esp,
            "Jefe Directo": v.user.manager.full_name if v.user.manager else "Sin Jefe"
        })
    
    return generate_excel_response(data, "Planificacion_Filtrada")

# --- REPORTE 2: HISTORIAL COMPLETO (Filtrado) ---
@router.get("/download/history", name="report_history")
def download_history(db: Session = Depends(get_db)):
    """
    Descarga historial, excluyendo usuarios que no corresponden.
    """
    eligible_users = get_eligible_users_query(db).all()
    eligible_ids = [u.id for u in eligible_users]

    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.user_id.in_(eligible_ids)
    ).order_by(models.VacationPeriod.created_at.desc()).all()
    
    data = []
    for v in vacations:
        data.append({
            "ID": v.id,
            "Empleado": v.user.full_name,
            "Área": v.user.area,
            "Inicio": v.start_date,
            "Fin": v.end_date,
            "Días": v.days,
            "Estado": v.status,
            "Fecha Solicitud": v.created_at.strftime("%Y-%m-%d")
        })
    
    return generate_excel_response(data, "Historial_Global")

# --- REPORTE 3: SALDOS (Filtrado) ---
@router.get("/download/balances", name="report_balances")
def download_balances(db: Session = Depends(get_db)):
    """
    Reporte de saldos SOLO de usuarios elegibles.
    """
    users = get_eligible_users_query(db).all()
    
    data = []
    for u in users:
        try:
            balance = crud.get_user_vacation_balance(db, u)
        except AttributeError:
            balance = u.vacation_days_total - u.vacation_days_taken

        data.append({
            "DNI/User": u.username,
            "Nombre Completo": u.full_name,
            "Área": u.area,
            "Rol": u.role,
            "Auto-Solicitud": "SÍ" if u.can_request_own_vacation else "NO",
            "Derecho Anual": u.vacation_days_total,
            "Saldo Disponible": balance
        })
    
    return generate_excel_response(data, "Reporte_Saldos")

# --- UTILIDAD EXCEL ---
def generate_excel_response(data: list, file_prefix: str):
    """Genera la respuesta StreamingResponse con el Excel."""
    if not data:
        df = pd.DataFrame([{"Mensaje": "No hay datos para este reporte"}])
    else:
        df = pd.DataFrame(data)
        
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        sheet_name = "Datos"
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        
        worksheet = writer.sheets[sheet_name]
        for column in df:
            col_idx = df.columns.get_loc(column)
            col_letter = chr(65 + col_idx)
            worksheet.column_dimensions[col_letter].width = 20

    stream.seek(0)
    filename = f"{file_prefix}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )