# app/api/__init__.py
# (VERSIÓN PARTE 7)

from fastapi import APIRouter
from .users import router as users_router
from .calculator import router as calculator_router # <-- NUEVO (PARTE 7)

api_router = APIRouter()
api_router.include_router(users_router, prefix="/users")
api_router.include_router(calculator_router) # <-- NUEVO (PARTE 7)