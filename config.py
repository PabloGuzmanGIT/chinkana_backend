import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'chinkana.db'}"
LOCAL_ID = int(os.getenv("LOCAL_ID", "1"))

SECRET_KEY = os.getenv("SECRET_KEY") or ""
if not SECRET_KEY:
    # Sin clave fija, las sesiones del admin se cierran cada vez que se reinicia la API.
    SECRET_KEY = secrets.token_hex(32)
    print("AVISO: SECRET_KEY vacío en .env; se usa una clave temporal.")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "chinkana123")

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

MEDIA_DIR = BASE_DIR / "media"
WEB_DIR = Path(os.getenv("WEB_DIR") or BASE_DIR.parent / "web" / "out")

CLIMA_CADA_MIN = 30      # cada cuánto la PC consulta el clima
CLIMA_VALIDO_HORAS = 6   # más viejo que esto = no se muestra la temperatura
