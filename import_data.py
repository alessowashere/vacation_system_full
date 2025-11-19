import os
import csv
from app import models
from app.db import SessionLocal
from sqlalchemy.orm import Session

# --- CONFIGURACIÓN ---
ADMIN_EMAIL = 'afernandezl@uandina.edu.pe'
HR_EMAIL = 'rhumanos@uandina.edu.pe'
CSV_FILENAME = "usuarios.csv"  # Tu archivo de 4 columnas

def import_data():
    print("🚀 INICIANDO CARGA (FORMATO SIMPLIFICADO 4 COLUMNAS)...")
    db: Session = SessionLocal()

    try:
        # 1. LIMPIEZA
        print("\n[1/4] Limpiando base de datos...")
        db.query(models.VacationLog).delete()
        db.query(models.SuspensionRequest).delete()
        db.query(models.ModificationRequest).delete()
        db.query(models.VacationPeriod).delete()
        db.query(models.User).update({models.User.manager_id: None})
        db.commit()
        db.query(models.User).delete()
        db.commit()
        print("✅ Base de datos limpia.")

        # 2. LECTURA
        print("\n[2/4] Leyendo archivo...")
        script_dir = os.path.dirname(__file__)
        csv_path = os.path.join(script_dir, CSV_FILENAME)

        users_to_create = {}
        relationships = []

        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            # Detectar si usa ; o ,
            line = f.readline()
            delimiter = ';' if ';' in line else ','
            f.seek(0)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            
            for row in reader:
                # Limpieza de datos
                email = row.get("CORREO", "").strip().lower()
                name = row.get("NOMBRES", "").strip()
                area = row.get("AREA", "").strip()
                boss_email = row.get("CORREO_JEFE", "").strip().lower()

                if not email or "@" not in email: continue

                # Guardar Empleado
                users_to_create[email] = {
                    "username": email.split('@')[0],
                    "full_name": name,
                    "email": email,
                    "role": "employee",
                    "area": area
                }
                
                # Guardar relación para después
                if boss_email and "@" in boss_email:
                    relationships.append((email, boss_email))
                    
                    # --- LA PARTE CLAVE: AUTO-CREAR JEFE FALTANTE ---
                    if boss_email not in users_to_create:
                        # Como NO tenemos el nombre del jefe en el CSV,
                        # creamos uno genérico usando su correo.
                        print(f"   ✨ Creando jefe fantasma: {boss_email}")
                        
                        users_to_create[boss_email] = {
                            "username": boss_email.split('@')[0],
                            "full_name": f"Jefe ({boss_email.split('@')[0]})", # Nombre generado
                            "email": boss_email,
                            "role": "manager",
                            "area": area # Asumimos el área del subordinado
                        }

        # 3. INSERCIÓN
        print(f"\n[3/4] Insertando {len(users_to_create)} usuarios...")
        
        # Roles especiales
        if ADMIN_EMAIL in users_to_create: users_to_create[ADMIN_EMAIL]["role"] = "admin"
        if HR_EMAIL in users_to_create: users_to_create[HR_EMAIL]["role"] = "hr"

        db_objects = []
        for data in users_to_create.values():
            u = models.User(
                username=data["username"],
                full_name=data["full_name"],
                email=data["email"],
                role=data["role"],
                area=data["area"],
                vacation_days_total=30
            )
            db_objects.append(u)
        
        db.add_all(db_objects)
        db.commit()
        print("✅ Usuarios creados.")

        # 4. VINCULACIÓN
        print("\n[4/4] Conectando jerarquías...")
        email_to_id = {u.email: u.id for u in db.query(models.User).all()}
        
        links = 0
        for emp_email, boss_email in relationships:
            emp_id = email_to_id.get(emp_email)
            boss_id = email_to_id.get(boss_email)
            
            if emp_id and boss_id:
                db.query(models.User).filter(models.User.id == emp_id).update({"manager_id": boss_id})
                links += 1
        
        db.commit()
        print(f"✅ {links} vínculos creados exitosamente.")

    except FileNotFoundError:
        print(f"❌ ERROR: No encuentro '{CSV_FILENAME}'")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        db.rollback()
    finally:
        db.close()
        print("\n✨ LISTO ✨")

if __name__ == "__main__":
    import_data()