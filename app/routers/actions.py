# app/routers/actions.py
# (VERSIÓN PARTE 10)

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os
from typing import Optional # Importar Optional

from app import crud, models
from app.auth import get_current_hr_user, get_current_manager_user, get_current_user
from app.db import get_db

router = APIRouter(
    prefix="/actions",
    tags=["Actions"],
    dependencies=[Depends(get_current_user)]
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

    if crud.check_edit_permission(vacation, current):
        crud.delete_vacation_period(db, vacation_id)
    else:
        pass 

    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/submit_area_to_hr", name="action_submit_area_to_hr")
async def submit_area_to_hr(
    request: Request,
    file: UploadFile = File(...),
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    uploads_dir = "uploads"
    file_name = f"CONSOLIDADO_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file_disk_path = os.path.join(uploads_dir, file_name)
    
    with open(file_disk_path, "wb") as f:
        f.write(await file.read())
        
    crud.submit_area_to_hr(db, area=current.area, file_name=file_name, actor=current)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

@router.post("/vacation/{vacation_id}/submit_individual", name="action_submit_individual")
def submit_individual_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation or vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")

    if not vacation.attached_file:
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg=No se puede enviar, el empleado no adjuntó documento."
        return RedirectResponse(url=error_url, status_code=302)
    
    if vacation.status == 'draft':
        crud.submit_individual_to_hr(db, vacation=vacation, actor=current)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/vacation/{vacation_id}/approve", name="action_approve_vacation")
def approve_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    crud.update_vacation_status(db, vacation=vacation, new_status="approved", actor=current)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/vacation/{vacation_id}/reject", name="action_reject_vacation")
def reject_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    vacation = crud.get_vacation_by_id(db, vacation_id)
    crud.update_vacation_status(db, vacation=vacation, new_status="rejected", actor=current)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

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
    if not vacation or vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")

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
    except Exception as e:
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg={str(e)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/approve", name="action_approve_modification")
def approve_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    crud.approve_modification(db, mod_id=mod_id, actor=current)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/reject", name="action_reject_modification")
def reject_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    crud.reject_modification(db, mod_id=mod_id, actor=current)
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
        
    if current.role == 'manager' and current.area != vacation.user.area:
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
    if not vacation or vacation.user.area != current.area:
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
    except Exception as e:
        error_url = str(request.url_for('dashboard')) + f"?error=general&msg={str(e)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/suspension/{sus_id}/approve", name="action_approve_suspension")
def approve_suspension(
    request: Request,
    sus_id: int,
    current=Depends(get_current_hr_user), # Solo HR
    db: Session = Depends(get_db)
):
    """Aprueba la solicitud de suspensión."""
    crud.approve_suspension(db, sus_id=sus_id, actor=current)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/suspension/{sus_id}/reject", name="action_reject_suspension")
def reject_suspension(
    request: Request,
    sus_id: int,
    current=Depends(get_current_hr_user), # Solo HR
    db: Session = Depends(get_db)
):
    """Rechaza la solicitud de suspensión."""
    crud.reject_suspension(db, sus_id=sus_id, actor=current)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)