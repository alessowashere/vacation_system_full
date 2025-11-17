# Sistema de Gestión de Vacaciones v2.0

Este es un sistema web integral para la gestión del flujo de solicitudes de vacaciones, diseñado para uso corporativo interno. La aplicación está construida con FastAPI y utiliza Docker para un despliegue sencillo.

La característica principal de esta versión es la integración total con **Google Workspace (OAuth 2.0)**, eliminando la necesidad de contraseñas locales y centralizando el acceso a través de las cuentas de correo institucionales.

## 🚀 Características Principales

* **Autenticación Segura:** Login exclusivo con Google (OAuth 2.0), restringido a un dominio corporativo (ej. `@uandina.edu.pe`).
* **Gestión de Roles:** Sistema de permisos robusto con 4 niveles:
    * **Empleado:** Crea solicitudes y ve sus propios estados.
    * **Manager (Jefe):** Ve el dashboard de su área, gestiona solicitudes de modificación y suspensión.
    * **HR (RRHH):** Aprueba o rechaza solicitudes finales, ve todos los dashboards.
    * **Admin:** Control total del sistema, incluyendo la gestión de usuarios.
* **Panel de Administración:**
    * **Gestión de Usuarios:** Crear, editar y asignar roles, áreas, días de vacaciones y jefes.
    * **Gestión de Feriados:** Añadir o eliminar días festivos.
    * **Ajustes del Sistema:** Configurar reglas de negocio (ej. permitir iniciar en fin de semana).
* **Flujo de Aprobación Completo:**
    * Empleado crea (Borrador).
    * Jefe envía a RRHH (Pendiente RRHH).
    * RRHH Aprueba o Rechaza.
    * Jefe puede solicitar Modificación o Suspensión de solicitudes aprobadas/rechazadas.
* **Carga Masiva de Datos:** Script para poblar toda la base de datos de usuarios y jerarquías desde un archivo CSV.
* **Base de Datos Modular:** Usa Alembic para manejar las migraciones de la base de datos.

## 🛠️ Stack Tecnológico

* **Backend:** FastAPI, SQLAlchemy, Alembic, Authlib, Uvicorn
* **Frontend:** Jinja2, Tailwind CSS
* **Base de Datos:** MySQL
* **Despliegue:** Docker, Docker Compose

## 📋 Guía de Instalación y Puesta en Marcha

Sigue estos pasos para levantar el proyecto desde cero.

### 1. Configuración de Google Cloud (Pre-requisito)

Antes de lanzar la aplicación, debes registrarla en Google Cloud para obtener las credenciales de OAuth.

1.  Ve a [console.cloud.google.com](https://console.cloud.google.com/) con tu cuenta de administrador de Google Workspace.
2.  Crea un **Proyecto Nuevo** (ej. "Sistema Vacaciones RRHH").
3.  Ve a **APIs y Servicios** > **Pantalla de consentimiento de OAuth**.
4.  Selecciona **"Interno"** como Tipo de Usuario y rellena los datos (Nombre de la app, correo de asistencia, etc.).
5.  En **"Dominios autorizados"**, añade `uandina.edu.pe`.
6.  Ve a **APIs y Servicios** > **Credenciales**.
7.  Haz clic en **+ Crear Credenciales** > **ID de cliente de OAuth**.
8.  Selecciona **"Aplicación web"**.
9.  En **"URIs de redireccionamiento autorizados"**, añade la URL exacta desde donde accederás al sistema.
    * **Ejemplo de tu configuración:** `http://dataepis.uandina.pe:49262/gestion/auth/google/callback`
10. Guarda y **copia tu `ID de cliente` y `Secreto de cliente`**.

### 2. Configuración del Proyecto

Edita el archivo `docker-compose.yml` para incluir tus credenciales.

```yaml
services:
  app:
    # ...
    environment:
      # ... (Configuración de la Base de Datos)
      - DB_HOST=vacation_db
      - DB_USER=admin
      - DB_PASSWORD=Redlabel@
      - DB_NAME=vacation_system
      
      # --- PEGA TUS CLAVES DE GOOGLE AQUÍ ---
      - GOOGLE_CLIENT_ID=TU_ID_DE_CLIENTE_VA_AQUI
      - GOOGLE_CLIENT_SECRET=TU_SECRETO_DE_CLIENTE_VA_AQUI
      
    # ...