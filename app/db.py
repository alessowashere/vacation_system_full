# app/db.py
# (VERSIÓN CORREGIDA - PARTE 7)

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

DB_HOST = os.getenv("DB_HOST","localhost")
DB_USER = os.getenv("DB_USER","admin")
DB_PASSWORD = os.getenv("DB_PASSWORD","Redlabel@")
DB_NAME = os.getenv("DB_NAME","vacation_system")

ENCODED_PASSWORD = quote_plus(DB_PASSWORD)

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- NUEVA FUNCIÓN (PARA DEPENDENCY INJECTION) ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()