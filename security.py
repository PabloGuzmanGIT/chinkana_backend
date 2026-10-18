"""Claves del staff (PBKDF2) y token de sesión firmado (HMAC). Solo librería estándar."""
import hashlib
import hmac
import secrets
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from config import LOCAL_ID, SECRET_KEY
from db import get_db
from models import Staff

_ITER = 200_000


def hash_clave(clave: str) -> str:
    sal = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), _ITER)
    return f"pbkdf2${sal}${dk.hex()}"


def verificar_clave(clave: str, guardada: str) -> bool:
    try:
        _, sal, hx = guardada.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), _ITER)
    return hmac.compare_digest(dk.hex(), hx)


def _firma(msg: str) -> str:
    return hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()


def crear_token(staff_id: int, horas: int = 12) -> str:
    msg = f"{staff_id}.{int(time.time()) + horas * 3600}"
    return f"{msg}.{_firma(msg)}"


def leer_token(token: str) -> int | None:
    try:
        staff_id, exp, firma = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(firma, _firma(f"{staff_id}.{exp}")) or int(exp) < time.time():
        return None
    return int(staff_id)


def staff_actual(authorization: str = Header(""), db: Session = Depends(get_db)) -> Staff:
    staff_id = leer_token(authorization.removeprefix("Bearer ").strip())
    staff = db.get(Staff, staff_id) if staff_id else None
    if not staff or not staff.activo or staff.local_id != LOCAL_ID:
        raise HTTPException(401, "Sesión vencida. Vuelve a ingresar.")
    return staff
