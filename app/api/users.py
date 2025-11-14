
from fastapi import APIRouter, Depends
from app.auth import get_current_user
router = APIRouter()

@router.get("/me")
def me(current=Depends(get_current_user)):
    return {"username": current.username, "role": current.role}
