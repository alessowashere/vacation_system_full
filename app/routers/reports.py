# app/routers/reports.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import pandas as pd
import io

from app import crud, models
from app.db import get_db
from app.auth import get_current_admin_user

# Creamos el router
router = APIRouter(
    prefix="/gestion/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin_user)] # Solo admins pueden ver esto
)

# --- VISTA HTML DEL PANEL DE REPORTES ---
@router.get("/", name="admin_reports_panel")
def reports_panel(db: Session = Depends(get_db)):
    # Redirigimos a la vista que ya tienes en admin o renderizamos directo.
    # Para mantenerlo simple, usaremos la ruta que definiremos en el template.
    from app.main import templates 
    from fastapi import Request
    # Nota: Si esto da error circular, moveremos esta vista a admin.py, 
    # pero por ahora úsala así o accede vía el botón del dashboard.
    return RedirectResponse(url="/gestion/admin/reports") 

# --- REPORTE 1: PLANIFICADOS (El que pediste) ---
@router.get("/download/planned", name="report_planned")
def download_planned(db: Session = Depends(get_db)):
    """
    Descarga reporte de vacaciones FUTURAS.
    CRITERIO: Desde hoy en adelante.
    ORDEN: Primero por Área (Oficina), luego por Fecha de Inicio.
    """
    today = date.today()
    
    # Consulta maestra: Unimos VacationPeriod con User para poder ordenar por Área
    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.start_date >= today,
        models.VacationPeriod.status.in_(['approved', 'pending_hr', 'pending_modification'])
    ).order_by(
        models.User.area.asc(),                 # 1. Agrupar por Oficina
        models.VacationPeriod.start_date.asc()  # 2. Ordenar por fecha más próxima
    ).all()
    
    data = []
    for v in vacations:
        # Traducimos los estados al español
        estado_esp = {
            "approved": "Aprobado",
            "pending_hr": "Pendiente RRHH",
            "pending_modification": "Solicita Cambio"
        }.get(v.status, v.status)

        data.append({
            "Área / Oficina": v.user.area or "Sin Área Asignada",
            "Empleado": v.user.full_name or v.user.username,
            "DNI/Usuario": v.user.username,
            "Fecha Inicio": v.start_date,
            "Fecha Fin": v.end_date,
            "Días": v.days,
            "Estado": estado_esp,
            "Jefe Directo": v.user.manager.full_name if v.user.manager else "Sin Jefe"
        })
    
    # Generar el Excel en memoria
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Planificación")
        
        # Ajuste cosmético de ancho de columnas
        worksheet = writer.sheets['Planificación']
        for column in df:
            column_width = max(df[column].astype(str).map(len).max(), len(column))
            col_idx = df.columns.get_loc(column)
            worksheet.column_dimensions[chr(65 + col_idx)].width = column_width + 2

    stream.seek(0)
    
    filename = f"Planificacion_Por_Areas_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- REPORTE 2: HISTORIAL COMPLETO ---
@router.get("/download/history", name="report_history")
def download_history(db: Session = Depends(get_db)):
    """Descarga TODO lo que ha pasado en el sistema (Histórico)."""
    vacations = db.query(models.VacationPeriod).join(models.User).order_by(models.VacationPeriod.created_at.desc()).all()
    
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
    
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Historial")
    stream.seek(0)
    
    filename = f"Historial_Global_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- REPORTE 3: SALDOS (Provisiones) ---
@router.get("/download/balances", name="report_balances")
def download_balances(db: Session = Depends(get_db)):
    """Reporte de cuántos días le quedan a cada empleado."""
    users = crud.get_all_users(db)
    
    data = []
    for u in users:
        balance = crud.get_user_vacation_balance(db, u)
        data.append({
            "DNI/User": u.username,
            "Nombre Completo": u.full_name,
            "Área": u.area,
            "Rol": u.role,
            "Derecho Anual": u.vacation_days_total,
            "Saldo Disponible": balance
        })
    
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Saldos")
    stream.seek(0)
    
    filename = f"Reporte_Saldos_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )