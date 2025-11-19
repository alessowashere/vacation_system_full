# app/utils/email.py
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from typing import List

# Configuración cargada desde las variables de entorno
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_FROM", "afernandezl@uandina.edu.pe"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True") == "True",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False") == "True",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_email_async(subject: str, email_to: List[str], body: str):
    """
    Envía un correo electrónico simple (texto/html).
    """
    message = MessageSchema(
        subject=subject,
        recipients=email_to,
        body=body,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    
    try:
        await fm.send_message(message)
        print(f"✅ Correo enviado a {email_to}")
        return True
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")
        return False