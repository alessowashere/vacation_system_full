# app/routers/actions.py
# (VERSIÓN PARTE 6)

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os

from app import crud, models
from app.auth import get_current_hr_user, get_current_manager_user, get_current_user
from app.db import SessionLocal

# Configuración del router
router = APIRouter(
    prefix="/gestion/actions",
    tags=["Actions"],
    dependencies=[Depends(get_current_user)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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

    is_owner = (vacation.user_id == current.id)
    is_manager = (current.role == 'manager' and vacation.user.area == current.area)
    
    if (is_owner or is_manager) and vacation.status == 'draft':
        crud.delete_vacation_period(db, vacation_id)
    else:
        pass # TODO: Redirigir con error

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
        
    crud.submit_area_to_hr(db, area=current.area, file_name=file_name)
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/vacation/{vacation_id}/approve", name="action_approve_vacation")
def approve_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    crud.update_vacation_status(db, vacation_id=vacation_id, new_status="approved")
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/vacation/{vacation_id}/reject", name="action_reject_vacation")
def reject_vacation(
    request: Request,
    vacation_id: int,
    current=Depends(get_current_hr_user),
    db: Session = Depends(get_db)
):
    crud.update_vacation_status(db, vacation_id=vacation_id, new_status="rejected")
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)

# --- NUEVAS RUTAS (PARTE 6) ---

@router.post("/vacation/{vacation_id}/modify", name="action_request_modification")
async def request_modification(
    request: Request,
    vacation_id: int,
    reason_text: str = Form(...),
    file: UploadFile = File(...),
    current=Depends(get_current_manager_user),
    db: Session = Depends(get_db)
):
    """
    Recibe el formulario de modificación del jefe.
    """
    # 1. Validar la vacación original
    vacation = crud.get_vacation_by_id(db, vacation_id)
    if not vacation or vacation.user.area != current.area:
        raise HTTPException(status_code=403, detail="No autorizado")

    # 2. Guardar el nuevo archivo adjunto
    uploads_dir = "uploads"
    file_name = f"MODIFICACION_{current.area}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file_disk_path = os.path.join(uploads_dir, file_name)
    
    with open(file_disk_path, "wb") as f:
        f.write(await file.read())
        
    # 3. Crear el registro en la BD
    crud.create_modification_request(
        db, 
        vacation_id=vacation_id,
        user=current,
        reason=reason_text,
        file_name=file_name
    )
    
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/approve", name="action_approve_modification")
def approve_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user), # Solo HR
    db: Session = Depends(get_db)
):
    """Aprueba la solicitud de modificación."""
    crud.approve_modification(db, mod_id=mod_id)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/modification/{mod_id}/reject", name="action_reject_modification")
def reject_modification(
    request: Request,
    mod_id: int,
    current=Depends(get_current_hr_user), # Solo HR
    db: Session = Depends(get_db)
):
    """Rechaza la solicitud de modificación."""
    crud.reject_modification(db, mod_id=mod_id)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)