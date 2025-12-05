from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os
from typing import Optional
from app import crud, models, schemas
from app.auth import get_current_user, get_current_manager_user, get_current_hr_user
from app.db import get_db
from app.utils.email import send_email_async  # Importamos la utilidad

def get_hr_emails(db: Session):
    hr_users = db.query(models.User).filter(models.User.role.in_(['hr', 'admin'])).all()
    return [u.email for u in hr_users if u.email]
router = APIRouter(
    prefix="/gestion/actions",
    tags=["Actions"]
)

@router.post("/vacation/{vacation_id}/delete", name="action_delete_vacation")
def delete_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    # Al usar esta función, hereda automáticamente el permiso "Manager Autónomo" que definimos arriba
    if crud.check_edit_permission(vacation, current):
        crud.delete_vacation_period(db, vacation_id)
    else:
        # Opcional: Podrías lanzar un error 403 aquí si prefieres feedback visual
        pass 

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


# En app/routers/actions.py

# En app/routers/actions.py

@router.post("/submit_area_to_hr", name="action_submit_area_to_hr")
async def submit_area_to_hr(
    request: Request,
    file: UploadFile = File(None),
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    uploads_dir = "uploads"
    file_name = None 

    if file and file.filename:
        # (Aquí iría la validación de tipo sugerida arriba)
        os.makedirs(uploads_dir, exist_ok=True)
        file_name = f"CONSOLIDADO_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_disk_path = os.path.join(uploads_dir, file_name)
        with open(file_disk_path, "wb") as f:
            f.write(await file.read())
        
    # Ejecutar la lógica de BD
    crud.submit_area_to_hr(db, area=current.area, file_name=file_name, actor=current)
    
    # --- NUEVO: ENVIAR CORREO A RRHH ---
    hr_emails = get_hr_emails(db)
    if hr_emails:
        adjunto_txt = "Se ha adjuntado documento consolidado." if file_name else "Sin documento consolidado."
        await send_email_async(
            subject=f"📦 Lote de Solicitudes Enviado: Equipo de {current.full_name}",
            email_to=hr_emails,
            body=f"""
            <div style="font-family: sans-serif;">
                <h3 style="color: #2980b9;">Nuevo Lote de Solicitudes</h3>
                <p>El Jefe <b>{current.full_name}</b> ha enviado un lote de solicitudes de su equipo para revisión.</p>
                <p><b>Estado:</b> Pendiente RRHH</p>
                <p>{adjunto_txt}</p>
                <hr>
                <p>Por favor ingrese al sistema para procesarlas.</p>
            </div>
            """
        )
    # -----------------------------------
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

@router.post("/vacation/{vacation_id}/submit_individual", name="action_submit_individual")
async def submit_individual_vacation(
    request: Request,
    vacation_id: int,
    file: UploadFile = File(None), # <--- CAMBIO: File(None) hace que sea opcional
    current: models.User = Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    """
    El JEFE envía la solicitud a RRHH (Documento Opcional).
    """
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado: No es tu subordinado")

    # --- ELIMINAMOS LA VALIDACIÓN QUE OBLIGABA A SUBIR ARCHIVO ---
    # if not file or not file.filename: ...

    file_name = None

    # Guardar archivo SOLO si existe
    if file and file.filename:
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in (' ._-'))
        file_name = f"INDIVIDUAL_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_filename}"
        file_disk_path = os.path.join(uploads_dir, file_name)

        try:
            content = await file.read()
            with open(file_disk_path, "wb") as f:
                f.write(content)
        except Exception as e:
            print(f"Error guardando archivo: {e}")
            raise HTTPException(status_code=500, detail="Error al guardar el archivo")

    # Actualizar estado en BD
    if vacation.status == 'draft':
        crud.submit_individual_to_hr(db, vacation=vacation, actor=current, file_name=file_name)
        
        # ... (lógica de emails se mantiene igual) ...
        hr_emails = get_hr_emails(db)
        if hr_emails:
            adjunto_txt = "Se ha adjuntado documento." if file_name else "Sin documento adjunto."
            await send_email_async(
                subject=f"📄 Solicitud Enviada a RRHH: {vacation.user.full_name}",
                email_to=hr_emails,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3>Nueva Solicitud Pendiente de Aprobación</h3>
                    <p>El Jefe <b>{current.full_name}</b> ha enviado la solicitud de <b>{vacation.user.full_name}</b>.</p>
                    <p>Estado: <b>Pendiente RRHH</b></p>
                    <p>{adjunto_txt}</p>
                    <a href="{str(request.url_for('login_page'))}" style="color:#3498db;">Ingresar al Sistema</a>
                </div>
                """
            )
        
    return RedirectResponse(url=str(request.url_for('dashboard')) + "?success_msg=Enviado a RRHH correctamente.", status_code=303)

# app/routers/actions.py

# ... (imports)

@router.post("/vacation/{vacation_id}/approve", name="action_approve_vacation")
async def approve_vacation(
    request: Request,
    vacation_id: int,
    current: models.User = Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    """
    RRHH aprueba la solicitud final.
    """
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    crud.update_vacation_status(db, vacation=vacation, new_status="approved", actor=current)
    
    # --- NOTIFICACIÓN AL EMPLEADO ---
    if vacation.user.email:
        formatted_start = vacation.start_date.strftime('%d/%m/%Y')
        formatted_end = vacation.end_date.strftime('%d/%m/%Y')
        
        await send_email_async(
            subject="✅ Solicitud de Vacaciones APROBADA",
            email_to=[vacation.user.email],
            body=f"""
            <div style="font-family: Arial, sans-serif; color: #333;">
                <h2 style="color: #2ecc71;">¡Tu solicitud ha sido Aprobada!</h2>
                <p>Hola <b>{vacation.user.full_name}</b>,</p>
                <p>La Dirección de Recursos Humanos ha aprobado tus vacaciones.</p>
                <hr>
                <p><b>📅 Desde:</b> {formatted_start}</p>
                <p><b>📅 Hasta:</b> {formatted_end}</p>
                
                <p><b>🗓️ Días:</b> {vacation.days}</p> 
                
                <hr>
                <p>Disfruta de tu descanso.</p>
                <p style="font-size: 12px; color: #777;">Sistema de Gestión de Vacaciones - UAndina</p>
            </div>
            """
        )

    return RedirectResponse(url=str(request.url_for("dashboard")) + "?success_msg=Solicitud Aprobada y notificada.", status_code=303)



@router.post("/vacation/{vacation_id}/reject", name="action_reject_vacation")
async def reject_vacation(
    request: Request,
    vacation_id: int,
    current: models.User = Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    """
    RRHH rechaza la solicitud.
    """
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    crud.update_vacation_status(db, vacation=vacation, new_status="rejected", actor=current)

    # --- NOTIFICACIÓN AL EMPLEADO ---
    if vacation.user.email:
        await send_email_async(
            subject="❌ Solicitud de Vacaciones RECHAZADA",
            email_to=[vacation.user.email],
            body=f"""
            <div style="font-family: Arial, sans-serif; color: #333;">
                <h2 style="color: #e74c3c;">Solicitud Rechazada</h2>
                <p>Hola <b>{vacation.user.full_name}</b>,</p>
                <p>Tu solicitud de vacaciones para las fechas {vacation.start_date} al {vacation.end_date} ha sido observada o rechazada por RRHH.</p>
                <p>Por favor, comunícate con tu jefe directo o con la oficina de RRHH para más detalles.</p>
            </div>
            """
        )

    return RedirectResponse(url=str(request.url_for("dashboard")) + "?success_msg=Solicitud Rechazada.", status_code=303)

@router.post("/vacation/{vacation_id}/modify", name="action_request_modification")
async def request_modification(
    request: Request,
    vacation_id: int,
    start_date: str = Form(...),
    period_type: int = Form(...),
    reason_text: str = Form(...),
    file: UploadFile = File(...),
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404)
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado: No es tu subordinado")

    uploads_dir = "uploads"
    file_name = f"MODIFICACION_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file_disk_path = os.path.join(uploads_dir, file_name)
    
    with open(file_disk_path, "wb") as f:
        f.write(await file.read())
        
    try:
        crud.create_modification_request(
            db, 
            vacation=vacation,
            user=current,
            reason=reason_text,
            file_name=file_name,
            new_start_date_str=start_date,
            new_period_type=period_type
        )
        hr_emails = get_hr_emails(db)
        if hr_emails:
            await send_email_async(
                subject=f"✏️ Solicitud de MODIFICACIÓN: {vacation.user.full_name}",
                email_to=hr_emails,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3>Solicitud de Modificación</h3>
                    <p>El Jefe <b>{current.full_name}</b> solicita modificar las vacaciones de <b>{vacation.user.full_name}</b>.</p>
                    <p><b>Motivo:</b> {reason_text}</p>
                    <p>Revise la sección "Pend. Modificación" en el dashboard.</p>
                </div>
                """
            )
    except Exception as e:
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg={str(e)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/approve", name="action_approve_modification")
async def approve_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    # crud.approve_modification devuelve el objeto mod_req actualizado
    mod_req = crud.approve_modification(db, mod_id=mod_id, actor=current)
    
    if mod_req:
        # Datos para el correo
        employee = mod_req.vacation_period.user
        manager = mod_req.requesting_user
        new_start = mod_req.new_start_date
        new_end = mod_req.new_end_date
        
        # Lista de destinatarios: Empleado y Jefe
        recipients = []
        if employee.email: recipients.append(employee.email)
        if manager.email and manager.email != employee.email: recipients.append(manager.email)
        
        if recipients:
            await send_email_async(
                subject="✅ Modificación de Vacaciones APROBADA",
                email_to=recipients,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3 style="color: #27ae60;">Modificación Aprobada</h3>
                    <p>La solicitud de modificación para <b>{employee.full_name}</b> ha sido aprobada por RRHH.</p>
                    <hr>
                    <p><b>Nuevas Fechas Confirmadas:</b></p>
                    <ul>
                        <li>Desde: {new_start}</li>
                        <li>Hasta: {new_end}</li>
                    </ul>
                    <p>El sistema ha sido actualizado.</p>
                </div>
                """
            )

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/reject", name="action_reject_modification")
async def reject_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    mod_req = crud.reject_modification(db, mod_id=mod_id, actor=current)
    
    if mod_req:
        employee = mod_req.vacation_period.user
        manager = mod_req.requesting_user
        
        recipients = []
        if employee.email: recipients.append(employee.email)
        if manager.email and manager.email != employee.email: recipients.append(manager.email)
        
        if recipients:
            await send_email_async(
                subject="❌ Modificación de Vacaciones RECHAZADA",
                email_to=recipients,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3 style="color: #c0392b;">Modificación Rechazada</h3>
                    <p>La solicitud de modificación para <b>{employee.full_name}</b> ha sido rechazada por RRHH.</p>
                    <p>Se mantienen las fechas originales (o el estado previo) de la vacación.</p>
                    <p>Por favor contactar con RRHH para más detalles.</p>
                </div>
                """
            )

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

@router.post("/vacation/{vacation_id}/comment", name="action_add_comment")
def add_comment(
    request: Request,
    vacation_id: int,
    log_text: str = Form(...),
    current=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current.role not in ['admin', 'hr', 'manager']:
        raise HTTPException(status_code=403, detail="No autorizado")

    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        
    if current.role == 'manager' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")

    crud.create_vacation_log(db, vacation=vacation, user=current, log_text=log_text)
    
    return RedirectResponse(
        url=request.url_for("vacation_details", vacation_id=vacation_id), 
        status_code=303
    )

# --- NUEVAS RUTAS (PARTE 10) ---

@router.post("/vacation/{vacation_id}/suspend", name="action_request_suspension")
async def request_suspension(
    request: Request,
    vacation_id: int,
    suspension_type: str = Form(...),
    reason_text: str = Form(...),
    file: UploadFile = File(...),
    new_end_date: Optional[str] = Form(None), # Campo opcional
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    """
    Recibe el formulario de solicitud de suspensión del jefe.
    """
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation: 
        raise HTTPException(status_code=404)
    if current.role != 'admin' and vacation.user.manager_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")

    uploads_dir = "uploads"
    file_name = f"SUSPENSION_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file_disk_path = os.path.join(uploads_dir, file_name)
    
    with open(file_disk_path, "wb") as f:
        f.write(await file.read())
        
    try:
        crud.create_suspension_request(
            db, 
            vacation=vacation,
            actor=current,
            suspension_type=suspension_type,
            reason=reason_text,
            file_name=file_name,
            new_end_date_str=new_end_date
        )
        hr_emails = get_hr_emails(db)
        if hr_emails:
            await send_email_async(
                subject=f"⏸️ Solicitud de SUSPENSIÓN: {vacation.user.full_name}",
                email_to=hr_emails,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3>Solicitud de Suspensión ({suspension_type})</h3>
                    <p>El Jefe <b>{current.full_name}</b> solicita suspender las vacaciones de <b>{vacation.user.full_name}</b>.</p>
                    <p><b>Motivo:</b> {reason_text}</p>
                    <p>Revise la sección "Pend. Suspensión" en el dashboard.</p>
                </div>
                """
            )
    except Exception as e:
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg={str(e)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/suspension/{sus_id}/approve", name="action_approve_suspension")
async def approve_suspension(
    request: Request,
    sus_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    """Aprueba la solicitud de suspensión."""
    sus_req = crud.approve_suspension(db, sus_id=sus_id, actor=current)
    
    if sus_req:
        employee = sus_req.vacation_period.user
        manager = sus_req.requesting_user
        tipo = sus_req.suspension_type.upper()
        
        recipients = []
        if employee.email: recipients.append(employee.email)
        if manager.email and manager.email != employee.email: recipients.append(manager.email)
        
        detalle_extra = ""
        if sus_req.suspension_type == 'parcial':
            detalle_extra = f"<p>Se ha recalculado el periodo. Nuevo fin: <b>{sus_req.new_end_date_parcial}</b></p>"
        else:
            detalle_extra = "<p>El periodo ha quedado suspendido y los días retornaron al saldo.</p>"

        if recipients:
            await send_email_async(
                subject=f"✅ Suspensión de Vacaciones APROBADA ({tipo})",
                email_to=recipients,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3 style="color: #27ae60;">Suspensión {tipo} Aprobada</h3>
                    <p>La solicitud de suspensión para <b>{employee.full_name}</b> ha sido procesada exitosamente.</p>
                    {detalle_extra}
                    <p>Saludos, RRHH.</p>
                </div>
                """
            )

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/suspension/{sus_id}/reject", name="action_reject_suspension")
async def reject_suspension(
    request: Request,
    sus_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    """Rechaza la solicitud de suspensión."""
    sus_req = crud.reject_suspension(db, sus_id=sus_id, actor=current)
    
    if sus_req:
        employee = sus_req.vacation_period.user
        manager = sus_req.requesting_user
        
        recipients = []
        if employee.email: recipients.append(employee.email)
        if manager.email and manager.email != employee.email: recipients.append(manager.email)
        
        if recipients:
            await send_email_async(
                subject="❌ Suspensión de Vacaciones RECHAZADA",
                email_to=recipients,
                body=f"""
                <div style="font-family: sans-serif;">
                    <h3 style="color: #c0392b;">Suspensión Rechazada</h3>
                    <p>La solicitud de suspensión para <b>{employee.full_name}</b> ha sido rechazada.</p>
                    <p>La vacación original sigue vigente y aprobada tal como estaba.</p>
                </div>
                """
            )

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

@router.post("/vacation/request", name="action_request_vacation")
async def request_vacation_create(
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    El Empleado crea la solicitud inicial (Draft).
    """
    # Convertir fechas
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(url=str(request.url_for('dashboard')) + "?error=Fechas inválidas", status_code=302)
    
    # Lógica de validación de saldo (simplificada, debería estar en logic/)
    # ...
    
    # Crear en BD
    try:
        new_vacation = crud.create_vacation_request(db, user_id=current.id, start_date=dt_start, end_date=dt_end)
    except Exception as e:
        return RedirectResponse(url=str(request.url_for('dashboard')) + f"?error={str(e)}", status_code=302)

    # --- NOTIFICACIÓN AL JEFE ---
    # Buscamos al jefe del usuario
    if current.manager and current.manager.email:
        approval_link = f"http://dataepis.uandina.pe:49262/gestion/" # Ajusta esta URL a tu IP real
        
        await send_email_async(
            subject=f"📩 Nueva Solicitud: {current.full_name}",
            email_to=[current.manager.email],
            body=f"""
            <div style="font-family: Arial, sans-serif;">
                <h3>Nueva Solicitud de Vacaciones</h3>
                <p>El colaborador <b>{current.full_name}</b> ({current.area}) ha solicitado vacaciones.</p>
                <ul>
                    <li><b>Desde:</b> {dt_start}</li>
                    <li><b>Hasta:</b> {dt_end}</li>
                </ul>
                <p>Por favor, ingresa al sistema para descargar el formato y tramitar la solicitud.</p>
                <a href="{approval_link}" style="background-color:#3498db; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Ir al Sistema</a>
            </div>
            """
        )

    return RedirectResponse(url=str(request.url_for('dashboard')) + "?success_msg=Solicitud creada exitosamente. Se notificó a tu jefe.", status_code=303)