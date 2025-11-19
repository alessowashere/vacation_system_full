import sys
import os
from app.db import SessionLocal
from app import models
from sqlalchemy import text

def reset_requests_only():
    print("🚀 INICIANDO LIMPIEZA DE SOLICITUDES (CONSERVANDO USUARIOS)...")
    db = SessionLocal()

    try:
        # 1. Eliminar Logs (Historial)
        print("   [1/4] Eliminando Historial (Logs)...")
        db.query(models.VacationLog).delete()
        
        # 2. Eliminar Solicitudes de Suspensión
        print("   [2/4] Eliminando Suspensiones...")
        db.query(models.SuspensionRequest).delete()
        
        # 3. Eliminar Solicitudes de Modificación
        print("   [3/4] Eliminando Modificaciones...")
        db.query(models.ModificationRequest).delete()
        
        # 4. Eliminar las Vacaciones en sí
        print("   [4/4] Eliminando Periodos de Vacaciones...")
        db.query(models.VacationPeriod).delete()
        
        db.commit()
        print("\n✅ ¡LISTO! Todas las solicitudes han sido borradas.")
        print("   (Los usuarios, jefes y configuraciones siguen intactos).")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_requests_only()