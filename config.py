import os
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'chinkana.db'}"
# Railway entrega postgresql://… y SQLAlchemy buscaría psycopg2; usamos psycopg 3.
for _prefijo in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_prefijo):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_prefijo):]
LOCAL_ID = int(os.getenv("LOCAL_ID", "1"))

# Hora del local. En la nube el servidor corre en UTC: sin esto las promos por horario saldrían 5 h adelantadas.
ZONA = ZoneInfo(os.getenv("ZONA_HORARIA", "America/Lima"))


def ahora() -> datetime:
    """Hora local del negocio, sin tzinfo (así se guarda en la BD)."""
    return datetime.now(ZONA).replace(tzinfo=None)

SECRET_KEY = os.getenv("SECRET_KEY") or ""
if not SECRET_KEY:
    # Sin clave fija, las sesiones del admin se cierran cada vez que se reinicia la API.
    SECRET_KEY = secrets.token_hex(32)
    print("AVISO: SECRET_KEY vacío en .env; se usa una clave temporal.")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
# Sin ADMIN_PASS no hay clave por defecto: se genera una y el seed la muestra en el log al crear el admin.
ADMIN_PASS = os.getenv("ADMIN_PASS") or ""
ADMIN_PASS_GENERADA = not ADMIN_PASS
if ADMIN_PASS_GENERADA:
    ADMIN_PASS = secrets.token_urlsafe(12)

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

MEDIA_DIR = BASE_DIR / "media"
WEB_DIR = Path(os.getenv("WEB_DIR") or BASE_DIR.parent / "web" / "out")

CLIMA_CADA_MIN = 30      # cada cuánto la PC consulta el clima
CLIMA_VALIDO_HORAS = 6   # más viejo que esto = no se muestra la temperatura

# Carta desde admintienda (el POS). Vacío = la carta se edita a mano en /admin.
ADMINTIENDA_URL = (os.getenv("ADMINTIENDA_URL") or "").rstrip("/")
ADMINTIENDA_API_KEY = os.getenv("ADMINTIENDA_API_KEY") or ""
ADMINTIENDA_SUCURSAL = os.getenv("ADMINTIENDA_SUCURSAL") or ""   # branchId de este local: stock y disponibilidad de aquí
CATALOGO_CADA_MIN = 3          # solo lo que cambió (updatedSince)
CATALOGO_COMPLETO_HORAS = 6    # completo: también saca lo que se borró en el POS
