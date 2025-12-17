# app/routers/reports.py

from fastapi import APIRouter, Depends, Request, BackgroundTasks, Form, Query
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, date
from typing import Optional, List
import pandas as pd
import io

from app import crud, models
from app.db import get_db
from app.auth import get_current_admin_user
from app.utils.email import send_email_async

# CORRECCIÓN: El prefix debe ser solo /reports. 
# Con root_path="/gestion", la ruta final es /gestion/reports/
router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin_user)]
)

templates = Jinja2Templates(directory="app/templates")

# --- FUNCIONES AUXILIARES ---

def get_base_query(db: Session):
    """Consulta base para el personal programable activo."""
    return db.query(models.User).filter(
        and_(
            models.User.is_active == True,
            or_(
                models.User.role == 'employee',
                and_(
                    models.User.role == 'manager',
                    models.User.can_request_own_vacation == True
                )
            )
        )
    )

# --- VISTA PRINCIPAL (TABLERO DE CONTROL) ---

@router.get("/", response_class=HTMLResponse, name="admin_reports_panel")
def reports_panel(
    request: Request, 
    search: Optional[str] = None,
    area_filter: Optional[str] = None,
    balance_status: List[str] = Query(None), 
    sort_by: Optional[str] = "balance_desc",
    db: Session = Depends(get_db)
):
    # 1. Obtener Áreas para el filtro
    all_areas = db.query(models.User.area).distinct().filter(models.User.area != None).all()
    areas_list = sorted([r[0] for r in all_areas])

    # 2. Query Base
    query = get_base_query(db)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.User.full_name.ilike(search_term),
                models.User.username.ilike(search_term),
                models.User.email.ilike(search_term)
            )
        )
    
    if area_filter:
        query = query.filter(models.User.area == area_filter)

    users_orm = query.all()
    
    # 3. LÓGICA DE ALERTAS (Restaurada por completo)
    # Detectar borradores atascados
    drafts = db.query(models.VacationPeriod).filter(models.VacationPeriod.status == 'draft').all()
    users_with_drafts = {vp.user_id for vp in drafts}
    
    # Detectar programación futura (aprobada o en RRHH)
    future_requests = db.query(models.VacationPeriod).filter(
        models.VacationPeriod.start_date >= date.today(),
        models.VacationPeriod.status.in_(['approved', 'pending_hr'])
    ).all()
    users_with_future = {vp.user_id for vp in future_requests}

    # 4. Procesamiento de saldos y verificaciones
    users_view = []
    for u in users_orm:
        balance = crud.get_user_vacation_balance(db, u)
        
        # Estas variables activan los botones de alerta en el template admin_reports.html
        is_stuck = (u.id in users_with_drafts)         # El jefe no ha enviado a RRHH
        has_future_plan = (u.id in users_with_future)  # Ya tiene algo programado
        needs_planning = (balance > 5)                 # Le quedan muchos días por programar

        if balance_status:
            keep = False
            if 'critical' in balance_status and balance >= 30: keep = True
            if 'warning' in balance_status and 15 <= balance < 30: keep = True
            if 'normal' in balance_status and 1 <= balance < 15: keep = True
            if 'zero' in balance_status and balance <= 0: keep = True
            if not keep: continue

        users_view.append({
            "user_obj": u,
            "balance": balance,
            "taken": u.vacation_days_total - balance,
            "is_stuck": is_stuck,
            "needs_planning": needs_planning,
            "has_future_plan": has_future_plan,
            "manager_id": u.manager_id
        })

    # 5. Ordenamiento
    if sort_by == "balance_desc":
        users_view.sort(key=lambda x: x["balance"], reverse=True)
    elif sort_by == "balance_asc":
        users_view.sort(key=lambda x: x["balance"])
    elif sort_by == "name":
        users_view.sort(key=lambda x: x["user_obj"].full_name or "")

    return templates.TemplateResponse("admin_reports.html", {
        "request": request,
        "users": users_view,
        "areas": areas_list,
        "filters": {
            "search": search, "area": area_filter, 
            "balance_status": balance_status or [], "sort_by": sort_by
        }
    })

# --- ACCIONES ---

@router.post("/remind/manager/{manager_id}/for/{employee_id}", name="remind_manager_context")
async def remind_manager_context(
    request: Request, manager_id: int, employee_id: int,
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    manager = crud.get_user_by_id(db, manager_id)
    employee = crud.get_user_by_id(db, employee_id)
    
    if manager and manager.email and employee:
        background_tasks.add_task(
            send_email_async,
            subject=f"URGENTE: Solicitud Pendiente - {employee.full_name}",
            email_to=[manager.email],
            body=f"<h3>Solicitud en Borrador</h3><p>Hola {manager.full_name}, el colaborador {employee.full_name} tiene una solicitud que requiere ser enviada a RRHH.</p>"
        )
    return RedirectResponse(url=request.headers.get("referer", "../"), status_code=303)

@router.post("/remind/employee/{user_id}", name="remind_employee_balance")
async def remind_employee_balance(
    request: Request, user_id: int, 
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, user_id)
    if user and user.email:
        balance = crud.get_user_vacation_balance(db, user)
        background_tasks.add_task(
            send_email_async,
            subject="Recordatorio: Programación de Vacaciones",
            email_to=[user.email],
            body=f"<p>Hola {user.full_name}, tienes {balance} días de vacaciones pendientes por programar.</p>"
        )
    return RedirectResponse(url=request.headers.get("referer", "../"), status_code=303)

# --- DESCARGAS (Restauradas para evitar NoMatchFound) ---

@router.get("/download/planned", name="report_planned")
def download_planned(db: Session = Depends(get_db)):
    today = date.today()
    eligible_users = get_base_query(db).all()
    eligible_ids = [u.id for u in eligible_users]
    vacations = db.query(models.VacationPeriod).join(models.User).filter(
        models.VacationPeriod.user_id.in_(eligible_ids),
        models.VacationPeriod.start_date >= today,
        models.VacationPeriod.status.in_(['approved', 'pending_hr', 'pending_modification'])
    ).all()
    data = [{"Área": v.user.area, "Empleado": v.user.full_name, "Inicio": v.start_date, "Fin": v.end_date, "Días": v.days, "Estado": v.status} for v in vacations]
    return generate_excel_response(data, "Planificacion_Futura")

@router.get("/download/history", name="report_history")
def download_history(db: Session = Depends(get_db)):
    vacations = db.query(models.VacationPeriod).all()
    data = [{"ID": v.id, "Empleado": v.user.full_name, "Área": v.user.area, "Inicio": v.start_date, "Fin": v.end_date, "Días": v.days, "Estado": v.status} for v in vacations]
    return generate_excel_response(data, "Historial_Global")

@router.get("/download/balances", name="report_balances")
def download_balances(db: Session = Depends(get_db)):
    users = get_base_query(db).all()
    data = [{"DNI": u.username, "Nombre": u.full_name, "Área": u.area, "Saldo": crud.get_user_vacation_balance(db, u)} for u in users]
    return generate_excel_response(data, "Reporte_Saldos")

def generate_excel_response(data: list, file_prefix: str):
    df = pd.DataFrame(data) if data else pd.DataFrame([{"Mensaje": "Sin datos"}])
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Datos")
    stream.seek(0)
    filename = f"{file_prefix}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})

# --- REPORTE MAESTRO (Respetando el COP Oficial) ---

COP_ORDENADO = [
    (1, "OFICINA DE AUDITORÍA"), (1, "DEFENSORÍA UNIVERSITARIA"), (1, "OFICINA DE AUDITORÍA ACADÉMICA"),
    (1, "RECTORADO"), (2, "OFICINA DE SECRETARÍA GENERAL"), (2, "DIRECCIÓN DE PLANIFICACIÓN Y DESARROLLO UNIVERSITARIO"),(3, "UNIDAD DE TRANSFORMACION DIGITAL"),
    (3, "UNIDAD DE PLANEAMIENTO Y PRESUPUESTO"), (3, "UNIDAD DE ORGANIZACION Y METODOS DE TRABAJO"), (3, "UNIDAD DE ESTADISTICA"),
    (2, "OFICINA DE ASESORÍA JURÍDICA"), (2, "DIRECCIÓN DE TECNOLOGÍAS DE INFORMACIÓN"), (3, "UNIDAD DE DESARROLLO DE PROYECTOS INFORMÁTICOS"),
    (3, "UNIDAD DE DISEÑO Y PROGRAMACIÓN"), (3, "UNIDAD DE PRODUCCIÓN Y SOPORTE INFORMÁTICO"), (2, "OFICINA DE MARKETING, PROMOCIÓN E IMAGEN INSTITUCIONAL"),
    (3, "UNIDAD DE MARKETING DIGITAL"), (3, "UNIDAD DE IMAGEN INSTITUCIONAL"), (1, "VICERRECTORADO ADMINISTRATIVO"),
    (2, "CENTROS DE PRODUCCIÓN DE BIENES Y SERVICIOS"), (3, "CENTRO DE IDIOMAS"), (3, "CENTRO DE FORMACIÓN EN TECNOLOGÍAS DE INFORMACIÓN"),
    (2, "DIRECCIÓN DE ADMINISTRACIÓN"), (3, "UNIDAD DE CONTABILIDAD"), (3, "UNIDAD DE TESORERÍA"), (3, "UNIDAD DE PATRIMONIO"),
    (3, "UNIDAD DE ABASTECIMIENTOS"), (3, "UNIDAD DE SERVICIOS GENERALES"), (2, "DIRECCIÓN DE RECURSOS HUMANOS"),
    (3, "UNIDAD DE CONTROL, DESARROLLO HUMANO Y ESCALAFÓN"), (3, "UNIDAD DE REMUNERACIONES"), (3, "UNIDAD DE SEGURIDAD Y SALUD EN EL TRABAJO"),
    (2, "DIRECCIÓN DE BIENESTAR UNIVERSITARIO"), (3, "UNIDAD DE SALUD"), (3, "UNIDAD DE SERVICIO SOCIAL"),
    (2, "OFICINA DE INFRAESTRUCTURA Y OBRAS"), (3, "UNIDAD DE PROYECTOS Y OBRAS"), (3, "UNIDAD DE MANTENIMIENTO"),
    (2, "DIRECCIÓN DE PROMOCIÓN DEL DEPORTE"), (3, "UNIDAD DE DEPORTE EN GENERAL Y RECREACIÓN"), (3, "UNIDAD DE DEPORTE DE ALTA COMPETENCIA"),
    (1, "VICERRECTORADO DE INVESTIGACIÓN"), (2, "OFICINA DE ASESORÍA EN GESTIÓN DE LA INVESTIGACIÓN"),
    (2, "COORDINACIÓN DE TRANSFERENCIA TECNOLÓGICA Y PATENTES"), (2, "INSTITUTO CIENTÍFICO DE INVESTIGACIÓN"),
    (3, "COORDINACIÓN CIENTÍFICA"), (3, "COORDINACIÓN DE INVESTIGACIÓN EN RESPONSABILIDAD SOCIAL UNIVERSITARIA"),
    (3, "CENTRO DE INVESTIGACIÓN ALTAMENTE ESPECIALIZADO DE BIOMÉDICAS"), (3, "BIOTERIO AUTOMATIZADO."),
    (2, "DIRECCIÓN DE GESTIÓN DE LA INVESTIGACIÓN Y DE LA PRODUCCIÓN INTELECTUAL"), (3, "COORDINACIÓN DE FOMENTO DE LA INVESTIGACIÓN"),
    (3, "COORDINACIÓN DE ADMINISTRACIÓN DE PROYECTOS DE INVESTIGACIÓN."), (3, "COORDINACIÓN EN PRODUCCIÓN INTELECTUAL."),
    (2, "DIRECCIÓN DE BIBLIOTECAS Y EDITORIAL UNIVERSITARIA"), (3, "COORDINACIÓN DE BIBLIOTECA"),
    (3, "BIBLIOTECA - FACULTAD DE DERECHO Y CIENCIA POLÍTICA"), (3, "BIBLIOTECA - FACULTAD DE INGENIERÍA"),
    (3, "BIBLIOTECA - FACULTAD DE CIENCIAS ECONÓMICAS, ADMINISTRATIVAS Y CONTABLES."),
    (3, "BIBLIOTECA - FACULTAD DE CIENCIAS SOCIALES Y EDUCACIÓN"), (3, "BIBLIOTECA - FACULTAD DE CIENCIAS DE LA SALUD"),
    (3, "BIBLIOTECA – ESCUELA DE POSGRADO"), (3, "COORDINACIÓN DE EDITORIAL UNIVERSITARIA."),
    (2, "DIRECCIÓN DE INNOVACIÓN Y EMPRENDIMIENTO."), (3, "COORDINACIÓN EN INNOVACIÓN Y EMPRENDIMIENTO."),
    (3, "COORDINACIÓN EN INCUBADORAS Y DESARROLLO DE CAPACIDADES EMPRESARIALES"), (1, "VICERRECTORADO ACADÉMICO"),
    (2, "COORDINACIÓN DE GESTIÓN CON LA SUNEDU"), (2, "DIRECCIÓN DE SERVICIOS ACADÉMICOS"), (3, "UNIDAD DE PROCESOS TÉCNICOS ACADÉMICOS"),
    (3, "UNIDAD DE REGISTRO CENTRAL Y ESTADÍSTICA ACADÉMICA"), (2, "DIRECCIÓN DE ADMISIÓN Y CENTRO PREUNIVERSITARIO"),
    (3, "UNIDAD DE ADMISIÓN Y PROCESOS TÉCNICOS"), (3, "COORDINACIÓN DEL CENTRO PREUNIVERSITARIO DE CONSOLIDACIÓN DEL PERFIL DEL INGRESANTE"),
    (2, "DIRECCIÓN DE DESARROLLO ACADÉMICO"), (3, "COORDINACIÓN DE DESARROLLO CURRICULAR Y FORMACIÓN CONTINUA"),
    (3, "COORDINACIÓN de TUTORÍA ACADÉMICA Y ATENCIÓN PSICOPEDAGÓGICA"), (3, "UNIDAD DE EDUCACIÓN VIRTUAL Y A DISTANCIA"),
    (2, "DIRECCIÓN DE CALIDAD ACADÉMICA Y ACREDITACIÓN UNIVERSITARIA"), (3, "COORDINACIÓN DE CALIDAD ACADÉMICA DE PRE Y POSGRADO"),
    (3, "COORDINACIÓN DE ACREDITACIÓN DE PRE Y POSGRADO"), (2, "DIRECCIÓN DE RESPONSABILIDAD SOCIAL Y EXTENSIÓN UNIVERSITARIA"),
    (3, "UNIDAD DE ATENCIÓN AL DESARROLLO FORMATIVO: ARTE Y CULTURA"), (3, "UNIDAD DE COOPERACIÓN PARA EL DESARROLLO SOSTENIBLE"),
    (3, "UNIDAD DE EXTENSIÓN UNIVERSITARIA"), (3, "COORDINACIÓN DEL SISTEMA DE SEGUIMIENTO AL EGRESADO Y GRADUADO DE LA UAC"),
    (2, "DIRECCIÓN DE COOPERACIÓN NACIONAL E INTERNACIONAL"), (3, "UNIDAD DE CONVENIOS Y BECAS DE ESTUDIO"),
    (3, "UNIDAD DE MOVILIDAD ACADÉMICA Y ADMINISTRATIVA"), (3, "COORDINACIÓN DE BECAS Y CRÉDITO INTERINSTITUCIONAL"),
    (2, "FACULTAD DE CIENCIAS Y HUMANIDADES"), (3, "LABORATORIO DE QUÍMICA"), (3, "LABORATORIO DE FÍSICA"),
    (3, "HUMANIDADES Y EDUCACIÓN"), (3, "TURISMO"), (3, "DEPARTAMENTO ACADÉMICO DE MATEMÁTICA, FÍSICA, QUÍMICA Y ESTADÍSTICA"),
    (3, "ESCUELA PROFESIONAL DE EDUCACIÓN"), (3, "ESCUELA PROFESIONAL DE TURISMO"), (3, "ESCUELA DE ESTUDIOS DE FORMACIÓN GENERAL"),
    (3, "UNIDAD DE INVESTIGACIÓN"), (2, "FACULTAD DE CIENCIAS DE LA SALUD"), (3, "CENTRO ESTOMATOLÓGICO"),
    (3, "CENTRO DE SALUD INTEGRAL"), (3, "LABORATORIO DE CIENCIAS BÁSICAS"), (3, "LABORATORIO DE SIMULACIÓN CLÍNICA"),
    (3, "LABORATORIO DE CIRUGÍA EXPERIMENTAL"), (3, "MEDICINA HUMANA"), (3, "ESTOMATOLOGÍA"),
    (3, "OBSTETRICIA Y ENFERMERÍA"), (3, "PSICOLOGÍA"), (3, "ESCUELA PROFESIONAL DE MEDICINA HUMANA"),
    (3, "ESCUELA PROFESIONAL DE ESTOMATOLOGÍA"), (3, "ESCUELA PROFESIONAL DE OBSTETRICIA"), (3, "ESCUELA PROFESIONAL DE PSICOLOGÍA"),
    (3, "ESCUELA PROFESIONAL DE ENFERMERÍA"), (3, "ESCUELA PROFESIONAL DE TECNOLOGÍA MÉDICA"), (2, "FACULTAD DE DERECHO Y CIENCIA POLÍTICA"),
    (3, "DERECHO"), (3, "ESCUELA PROFESIONAL DE DERECHO"), (2, "FACULTAD DE CIENCIAS ECONÓMICAS, ADMINISTRATIVAS Y CONTABLES"),
    (3, "ECONOMÍA"), (3, "ADMINISTRACIÓN"), (3, "CONTABILIDAD"), (3, "ESCUELA PROFESIONAL DE ECONOMÍA"),
    (3, "ESCUELA PROFESIONAL DE ADMINISTRACIÓN"), (3, "ESCUELA PROFESIONAL DE CONTABILIDAD"), (3, "ESCUELA PROFESIONAL DE ADMINISTRACIÓN DE NEGOCIOS INTERNACIONALES"),
    (3, "ESCUELA PROFESIONAL DE FINANZAS"), (3, "ESCUELA PROFESIONAL DE MARKETING"), (2, "FACULTAD DE INGENIERÍA Y ARQUITECTURA"),
    (3, "LABORATORIOS DE INGENIERÍA INDUSTRIAL"), (3, "LABORATORIOS DE INGENIERÍA CIVIL"), (3, "LABORATORIO DE INGENIERÍA DE SISTEMAS"),
    (3, "INGENIERÍA INDUSTRIAL"), (3, "INGENIERÍA DE SISTEMAS"), (3, "INGENIERÍA CIVIL"), (3, "ARQUITECTURA"), (3, "INGENIERÍA AMBIENTAL"),
    (3, "ESCUELA PROFESIONAL DE INGENIERÍA INDUSTRIAL"), (3, "ESCUELA PROFESIONAL DE INGENIERÍA DE SISTEMAS"), (3, "ESCUELA PROFESIONAL DE INGENIERÍA CIVIL"),
    (3, "ESCUELA PROFESIONAL DE ARQUITECTURA"), (3, "ESCUELA PROFESIONAL DE INGENIERÍA AMBIENTAL"), (2, "ESCUELA DE POSGRADO"),
    (3, "COORDINACIÓN GENERAL DE LOS PROGRAMAS DE POSGRADO"), (3, "UNIDAD DE POSGRADO"), (3, "UNIDAD DE INVESTIGACIÓN"),
    (1, "FILIAL PUERTO MALDONADO"), (1, "FILIAL QUILLABAMBA"), (1, "FILIAL SICUANI")
]

@router.get("/master", response_class=HTMLResponse, name="admin_master_report")
def master_report(request: Request, db: Session = Depends(get_db)):
    all_users = get_base_query(db).all()
    users_by_area = {}
    for u in all_users:
        area_key = (u.area or "SIN ÁREA").strip().upper()
        if area_key not in users_by_area: users_by_area[area_key] = []
        balance = crud.get_user_vacation_balance(db, u)
        vacations = db.query(models.VacationPeriod).filter(models.VacationPeriod.user_id == u.id).order_by(models.VacationPeriod.start_date.asc()).all()
        users_by_area[area_key].append({"user": u, "balance": balance, "vacations": vacations})

    # CORRECCIÓN: Itera sobre el COP oficial. Si no hay personal, igual añade la sección (miembros vacíos).
    reporte_final = []
    for nivel, nombre_cop in COP_ORDENADO:
        miembros = users_by_area.get(nombre_cop.upper(), [])
        reporte_final.append({
            "nivel": nivel,
            "nombre": nombre_cop,
            "miembros": miembros # Si está vacío, el template mostrará "Sin personal"
        })
    return templates.TemplateResponse("admin_master_report.html", {"request": request, "report": reporte_final})