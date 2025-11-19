import os
import csv
from app import models
from app.db import SessionLocal
from sqlalchemy.orm import Session

# --- CONFIGURACIÓN ---
ADMIN_EMAIL = 'afernandezl@uandina.edu.pe'
HR_EMAIL = 'rhumanos@uandina.edu.pe'
CSV_FILENAME = "usuarios.csv"

def import_data():
    print("🚀 INICIANDO CARGA (CON NOMBRES DE JEFES)...")
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
            # Detectar delimitador automáticamente (; o ,)
            line = f.readline()
            delimiter = ';' if ';' in line else ','
            f.seek(0)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            
            for row in reader:
                # Limpieza de datos del empleado
                email = row.get("CORREO", "").strip().lower()
                name = row.get("NOMBRES", "").strip()
                area = row.get("AREA", "").strip()
                
                # Limpieza de datos del jefe
                boss_email = row.get("CORREO_JEFE", "").strip().lower()
                boss_name = row.get("NOMBRE_JEFE", "").strip() # <--- CAPTURAR NOMBRE DEL JEFE

                if not email or "@" not in email: continue

                # Guardar Empleado Principal
                # (Si ya existe, se actualiza con los datos de esta fila)
                users_to_create[email] = {
                    "username": email.split('@')[0],
                    "full_name": name,
                    "email": email,
                    "role": "employee", # Se ajustará a manager más abajo si corresponde
                    "area": area
                }
                
                # Procesar Jefe
                if boss_email and "@" in boss_email:
                    relationships.append((email, boss_email))
                    
                    # Si el jefe NO está en la lista de usuarios aún, lo creamos (Fantasma)
                    if boss_email not in users_to_create:
                        
                        # Usar el nombre del CSV si existe, sino uno genérico
                        final_boss_name = boss_name if boss_name else f"Jefe ({boss_email.split('@')[0]})"
                        
                        print(f"   ✨ Creando jefe fantasma: {boss_email} -> {final_boss_name}")
                        
                        users_to_create[boss_email] = {
                            "username": boss_email.split('@')[0],
                            "full_name": final_boss_name, # <--- AQUI USAMOS EL NOMBRE REAL
                            "email": boss_email,
                            "role": "manager",
                            "area": area # Asumimos el área del subordinado
                        }
                    
                    # Si el jefe YA existe (porque se cargó como empleado antes o después), 
                    # nos aseguramos de que tenga el rol de manager.
                    elif users_to_create[boss_email]["role"] == "employee":
                        users_to_create[boss_email]["role"] = "manager"

        # 3. INSERCIÓN
        print(f"\n[3/4] Insertando {len(users_to_create)} usuarios...")
        
        # Asignar Roles Especiales (Admin / HR)
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
        print(f"❌ ERROR: No encuentro '{CSV_FILENAME}' en la carpeta.")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        db.rollback()
    finally:
        db.close()
        print("\n✨ CARGA COMPLETA ✨")

if __name__ == "__main__":
    import_data()