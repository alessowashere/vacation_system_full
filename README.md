
Vacation System - FastAPI (Minimal Full)
=======================================

What is this:
- FastAPI app with MySQL (SQLAlchemy) and JWT auth
- Basic HTML UI (Jinja2 + forms) for login, dashboards and simple vacation flows
- File uploads saved to ./uploads
- Dockerfile + docker-compose for local deploy (includes MySQL service)

Quick start (using your VM):
1. Upload `vacation_system_full.zip` and unzip:
   unzip vacation_system_full.zip && cd vacation_system
2. Build and start with docker-compose (recommended for first run):
   sudo docker-compose up -d --build
3. The app will be available on port 8000 inside the VM. If your Proxmox maps public port 49262 -> VM:80,
   configure NGINX to proxy /gestion/ -> http://127.0.0.1:8000/

Environment variables (can be set in docker-compose or host):
- DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
- SECRET_KEY (very important, change in production)

Admin user:
- The docker-compose creates a MySQL user `admin` with password `Redlabel@` and DB `vacation_system`.
- An initial admin user will be created on first run if not present (username: admin, password: Redlabel@).

Notes:
- Change secrets before production.
- For production use a managed MySQL or secure your MySQL root password.
