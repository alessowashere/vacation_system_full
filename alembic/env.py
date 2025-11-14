# --- AÑADIR ESTAS LÍNEAS AL INICIO ---
import sys
import os
# Añade el directorio raíz del proyecto (un nivel arriba de 'alembic') al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- FIN DE LAS LÍNEAS A AÑADIR ---


from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- MI CONFIGURACIÓN ---
# 1. Importar la Base de nuestros modelos y la URL de la BD
from app.db import Base, DATABASE_URL
from app.models import User, Holiday, VacationPeriod # Importar todos los modelos

# Configuración de Alembic
config = context.config

# 2. Establecer la URL de la base de datos desde nuestro app/db.py
# --- MODIFICACIÓN ---
# Escapa los caracteres '%' (p.ej. en la contraseña) duplicándolos a '%%'
# para que el configparser de Alembic no falle.
alembic_db_url = DATABASE_URL.replace('%', '%%')
config.set_main_option('sqlalchemy.url', alembic_db_url)

# 3. Apuntar a los metadatos de nuestros modelos
target_metadata = Base.metadata
# --- FIN DE MI CONFIGURACIÓN ---


if config.config_file_name is not None:
    #fileConfig(config.config_file_name)
    pass

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()