# app/routers/reports.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import pandas as pd
import io

from app import crud, models
from app.db import get_db
from app.auth import get_current_admin_user
from app.utils.email import send_email_async

router = APIRouter(
    prefix="/gestion/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin_user)]
)

# --- VISTA PRINCIPAL DE REPORTES ---
@router.get("/panel", name="admin_reports_panel")
def reports_panel(db: Session = Depends(get_db)):
    from app.main import templates
    from fastapi import Request
    # Truco para obtener el request actual si no se pasa explícitamente (o pásalo en la def)
    # Para simplificar, asumiremos que se llama desde el navegador
    return RedirectResponse(url="/gestion/admin/reports") # Redirigimos a una ruta que definiremos en main

# --- GENERADORES DE EXCEL ---

@router.get("/download/history", name="report_history")
def download_history(db: Session = Depends(get_db)):
    """Descarga historial completo: Aprobados, Rechazados, Suspendidos, etc."""
    vacations = db.query(models.VacationPeriod).all()
    
    data = []
    for v in vacations:
        data.append({
            "ID Solicitud": v.id,
            "Empleado": v.user.full_name or v.user.username,
            "Área": v.user.area,
            "Fecha Inicio": v.start_date,
            "Fecha Fin": v.end_date,
            "Días": v.days,
            "Estado": v.status,
            "Solicitado el": v.created_at.strftime("%Y-%m-%d")
        })
    
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Historial")
    stream.seek(0)
    
    filename = f"Historial_Vacaciones_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/download/planned", name="report_planned")
def download_planned(db: Session = Depends(get_db)):
    """Descarga solo vacaciones aprobadas futuras (Planificadas)."""
    today = date.today()
    vacations = db.query(models.VacationPeriod).filter(
        models.VacationPeriod.status == 'approved',
        models.VacationPeriod.start_date >= today
    ).order_by(models.VacationPeriod.start_date).all()
    
    data = []
    for v in vacations:
        data.append({
            "Empleado": v.user.full_name or v.user.username,
            "Área": v.user.area,
            "Fecha Inicio": v.start_date,
            "Fecha Fin": v.end_date,
            "Días": v.days,
            "Jefe Directo": v.user.manager.full_name if v.user.manager else "Sin Jefe"
        })
    
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Planificados")
    stream.seek(0)
    
    filename = f"Planificados_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/download/balances", name="report_balances")
def download_balances(db: Session = Depends(get_db)):
    """Descarga reporte de saldos de todos los empleados."""
    users = crud.get_all_users(db)
    
    data = []
    for u in users:
        balance = crud.get_user_vacation_balance(db, u)
        data.append({
            "ID Empleado": u.id,
            "Nombre": u.full_name or u.username,
            "Email": u.email,
            "Área": u.area,
            "Rol": u.role,
            "Total Derecho": u.vacation_days_total,
            "Saldo Disponible": balance
        })
    
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Saldos")
    stream.seek(0)
    
    filename = f"Saldos_Personal_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- RECORDATORIOS ---

async def send_reminders_task(db: Session):
    """Tarea en segundo plano para enviar correos."""
    users = crud.get_all_users(db)
    count = 0
    for u in users:
        # Lógica: Enviar si tiene más de 10 días pendientes
        balance = crud.get_user_vacation_balance(db, u)
        if balance > 10 and u.email:
            subject = "📅 Recordatorio: Planifica tus Vacaciones"
            body = f"""
            <div style="font-family: Arial, sans-serif;">
                <h3 style="color: #2980b9;">Recordatorio de Vacaciones</h3>
                <p>Hola <b>{u.full_name}</b>,</p>
                <p>Te recordamos que aún tienes <b>{balance} días</b> de vacaciones disponibles.</p>
                <p>Por favor, coordina con tu jefe directo para planificar tu descanso antes del cierre del periodo.</p>
                <br>
                <p>Atte, <br>Recursos Humanos</p>
            </div>
            """
            await send_email_async(subject, [u.email], body)
            count += 1
    print(f"✅ Se enviaron {count} recordatorios.")

@router.post("/remind/all", name="action_send_reminders")
async def trigger_reminders(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Endpoint para disparar el envío masivo de recordatorios."""
    # Usamos BackgroundTasks para no bloquear la respuesta
    background_tasks.add_task(send_reminders_task, db)
    # Retornamos éxito inmediato
    return RedirectResponse(url="/gestion/admin/reports?success_msg=Recordatorios enviándose en segundo plano.", status_code=303)