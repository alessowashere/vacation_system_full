import sys
import os
from datetime import date
from app.db import SessionLocal
from app import models

def seed_2026():
    print("📅 CARGANDO FERIADOS 2026 (GENERALES Y FILIALES)...")
    db = SessionLocal()

    # 1. Limpiar feriados de 2026 para evitar duplicados
    # (Borramos todo 2026 para recargar limpio)
    db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= date(2026, 1, 1),
        models.Holiday.holiday_date <= date(2026, 12, 31)
    ).delete()
    db.commit()

    holidays = []

    # --- FERIADOS GENERALES (CUSCO Y TODAS LAS SEDES) ---
    # Fechas calculadas para el calendario 2026
    generales = [
        (date(2026, 1, 1), "Año Nuevo"),
        (date(2026, 4, 2), "Jueves Santo"),       # Móvil: Pascua es 5 Abril
        (date(2026, 4, 3), "Viernes Santo"),      # Móvil
        (date(2026, 5, 1), "Día del Trabajo"),
        (date(2026, 5, 23), "Aniversario UAC"),
        (date(2026, 6, 4), "Corpus Christi"),     # Móvil: 60 días después de Pascua
        (date(2026, 6, 7), "Día de la Bandera"),
        (date(2026, 6, 24), "Inti Raymi"),
        (date(2026, 6, 29), "San Pedro y San Pablo"),
        (date(2026, 7, 11), "Día del Docente Universitario"),
        (date(2026, 7, 21), "Día del Trabajador Universitario"),
        (date(2026, 7, 23), "Día de la Fuerza Aérea"),
        (date(2026, 7, 28), "Fiestas Patrias"),
        (date(2026, 7, 29), "Fiestas Patrias"),
        (date(2026, 8, 6), "Batalla de Junín"),
        (date(2026, 8, 30), "Santa Rosa de Lima"),
        (date(2026, 10, 8), "Combate de Angamos"),
        (date(2026, 11, 1), "Todos los Santos"),
        (date(2026, 11, 2), "Día de los Difuntos"),
        (date(2026, 12, 8), "Inmaculada Concepción"),
        (date(2026, 12, 9), "Batalla de Ayacucho"),
        (date(2026, 12, 24), "Víspera de Navidad"),
        (date(2026, 12, 25), "Navidad"),
    ]

    for dt, name in generales:
        # location="GENERAL" aplica a todos según la lógica nueva
        holidays.append(models.Holiday(holiday_date=dt, name=name, is_national=True, location="GENERAL"))

    # --- FILIAL PUERTO MALDONADO ---
    p_maldonado = [
        (date(2026, 5, 23), "Aniversario Filial Puerto Maldonado"),
        (date(2026, 6, 24), "Día de San Juan"),
        (date(2026, 8, 8), "Festival de la Castaña"),
        (date(2026, 9, 27), "Festival Sine Do Dari"),
        (date(2026, 12, 26), "Creación Política Madre de Dios"),
    ]
    for dt, name in p_maldonado:
        holidays.append(models.Holiday(holiday_date=dt, name=name, is_national=False, location="P_MALDONADO"))

    # --- FILIAL QUILLABAMBA ---
    quillabamba = [
        (date(2026, 7, 25), "Aniversario Prov. La Convención"),
        (date(2026, 9, 26), "Aniversario Filial Quillabamba"),
        (date(2026, 11, 28), "Aniv. Villa Quillabamba (Día 1)"),
        (date(2026, 11, 29), "Aniv. Villa Quillabamba (Día 2)"),
    ]
    for dt, name in quillabamba:
        holidays.append(models.Holiday(holiday_date=dt, name=name, is_national=False, location="QUILLABAMBA"))

    # --- FILIAL SICUANI ---
    sicuani = [
        (date(2026, 4, 15), "Aniversario Filial Sicuani"),
        (date(2026, 10, 14), "Aniversario Prov. Canchis"),
        (date(2026, 11, 4), "Aniversario Distrito Sicuani"),
    ]
    for dt, name in sicuani:
        holidays.append(models.Holiday(holiday_date=dt, name=name, is_national=False, location="SICUANI"))

    db.add_all(holidays)
    db.commit()
    print(f"✅ Carga Completa: Se han insertado {len(holidays)} feriados para el año 2026.")
    db.close()

if __name__ == "__main__":
    seed_2026()