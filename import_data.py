import os
import csv
from app import models
from app.db import SessionLocal, Base, engine
from sqlalchemy.orm import Session

# --- PASO 1: CONFIGURAR LOS CORREOS ---
ADMIN_EMAIL = 'afernandezl@uandina.edu.pe'
HR_EMAIL = 'rhumanos@uandina.edu.pe'
# ----------------------------------------

CSV_FILENAME = "BD PARA SISTEMA - ROL ANUAL - PARA SUBIR BD 2026.csv"

def import_data():
    print("Iniciando la importación de datos...")
    db: Session = SessionLocal()

    try:
        # --- Limpiar todas las tablas ---
        print("Limpiando datos antiguos...")
        db.query(models.VacationLog).delete()
        db.query(models.SuspensionRequest).delete()
        db.query(models.ModificationRequest).delete()
        db.query(models.VacationPeriod).delete()
        
        # --- ¡¡SOLUCIÓN AL ERROR!! ---
        # 1. Romper la dependencia circular (jefes)
        print("  > Rompiendo vínculos de managers existentes...")
        db.query(models.User).update({models.User.manager_id: None})
        db.commit()
        # --- FIN DE LA SOLUCIÓN ---

        # 2. Ahora sí podemos borrar a los usuarios
        db.query(models.User).delete()
        db.commit()
        print("Datos antiguos eliminados.")

        # --- PASS 1: Leer CSV y crear todos los usuarios ---
        print(f"PASS 1: Leyendo {CSV_FILENAME} y creando usuarios...")
        
        script_dir = os.path.dirname(__file__)
        csv_path = os.path.join(script_dir, CSV_FILENAME)

        all_user_data = []
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            all_user_data = list(reader)

        email_to_boss_email_map = {}
        all_boss_emails = set()
        
        for row in all_user_data:
            # Limpieza de email (para corregir el "afernandez,l@...")
            email = row["CORREO_EMP"].strip().lower().replace('"', '').replace(',', '')
            
            if not email or '@' not in email:
                print(f"  > Saltando fila inválida (sin email): {row['APELLIDOS Y NOMBRES']}")
                continue

            username = email.split('@')[0]

            # Determinar el rol
            role = 'employee' # Por defecto
            if email == ADMIN_EMAIL:
                role = 'admin'
            elif email == HR_EMAIL:
                role = 'hr'
            
            new_user = models.User(
                username=username,
                full_name=row["APELLIDOS Y NOMBRES"].strip(),
                email=email,
                role=role,
                area=row["DEPENDENCIA"].strip(),
                vacation_days_total=30 
            )
            db.add(new_user)
            
            # Guardar datos para pases futuros
            boss_email = row["CORREO JEFE"].strip().lower()
            if boss_email and boss_email != '-':
                email_to_boss_email_map[email] = boss_email
                all_boss_emails.add(boss_email)

        db.commit()
        print(f"  > {len(all_user_data)} usuarios creados en la BD.")

        # --- PASS 2: Asignar roles de 'manager' ---
        print("PASS 2: Asignando roles de 'manager'...")
        
        # Obtener todos los usuarios que acabamos de crear
        users_in_db = db.query(models.User).all()
        user_map_by_email = {u.email: u for u in users_in_db}
        
        managers_assigned = 0
        for email in all_boss_emails:
            if email in user_map_by_email:
                user = user_map_by_email[email]
                if user.role == 'employee': # Solo ascender si es 'employee'
                    user.role = 'manager'
                    managers_assigned += 1
            else:
                print(f"  > Advertencia (Rol Manager): El jefe '{email}' no se encuentra en la lista de usuarios.")
        
        db.commit()
        print(f"  > {managers_assigned} usuarios ascendidos a 'manager'.")
        
        # --- PASS 3: Vincular empleados con sus jefes ---
        print("PASS 3: Vinculando empleados con sus jefes...")
        
        links_made = 0
        for email, boss_email in email_to_boss_email_map.items():
            employee = user_map_by_email.get(email)
            manager = user_map_by_email.get(boss_email)
            
            if employee and manager:
                employee.manager_id = manager.id
                links_made += 1
            elif employee and not manager:
                # Esta advertencia SÍ es normal, si el jefe no está en la lista
                print(f"  > Advertencia (Vínculo): El jefe '{boss_email}' del empleado '{email}' no existe. No se pudo vincular.")
            
        db.commit()
        print(f"  > {links_made} vinculaciones de jefe-empleado realizadas.")

    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo '{CSV_FILENAME}'.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Ocurrió un error. Revirtiendo cambios: {str(e)}")
    finally:
        db.close()
        print("Importación finalizada. Conexión cerrada.")

if __name__ == "__main__":
    import_data()