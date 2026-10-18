"""Rutas públicas: las usa el celular del cliente (antes de tener internet) y el login.html del MikroTik."""
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import LOCAL_ID
from db import get_db
from models import Cliente, Dispositivo
from services import landing

router = APIRouter()

RE_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
RE_CEL = re.compile(r"^9\d{8}$")

# PNG transparente de 1×1. El login.html del MikroTik lo carga para saber si la PC está prendida.
def _png_1x1() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


PING_PNG = _png_1x1()
SIN_CACHE = {"Cache-Control": "no-store, max-age=0"}


@router.get("/api/health")
def health():
    return {"ok": True, "hora": datetime.now().isoformat(timespec="seconds")}


@router.get("/ping.png")
def ping():
    return Response(PING_PNG, media_type="image/png", headers=SIN_CACHE)


@router.get("/api/landing")
def get_landing(db: Session = Depends(get_db)):
    return landing.construir(db)


class Registro(BaseModel):
    telefono: str
    acepta_terminos: bool
    mac: str | None = None


@router.post("/api/portal/registro")
def registro(datos: Registro, db: Session = Depends(get_db)):
    """Guarda el WhatsApp. No abre la sesión: eso lo hace el navegador del cliente contra el MikroTik."""
    if not datos.acepta_terminos:
        raise HTTPException(400, "Debes aceptar los términos.")
    cel = re.sub(r"\D", "", datos.telefono)
    if len(cel) == 11 and cel.startswith("51"):
        cel = cel[2:]
    if not RE_CEL.match(cel):
        raise HTTPException(400, "Ingresa un celular de 9 dígitos que empiece con 9.")
    telefono = "51" + cel
    ahora = datetime.now()

    cliente = db.scalar(select(Cliente).where(Cliente.local_id == LOCAL_ID, Cliente.telefono == telefono))
    nuevo = cliente is None
    if nuevo:
        cliente = Cliente(local_id=LOCAL_ID, telefono=telefono, creado=ahora, visitas=0)
        db.add(cliente)
    cliente.visitas += 1
    cliente.ultima_visita = ahora
    cliente.acepto_terminos = ahora
    db.flush()

    mac = (datos.mac or "").upper()
    if RE_MAC.match(mac):
        disp = db.scalar(select(Dispositivo).where(Dispositivo.local_id == LOCAL_ID, Dispositivo.mac == mac))
        if not disp:
            disp = Dispositivo(local_id=LOCAL_ID, mac=mac, primera_vez=ahora)
            db.add(disp)
        disp.cliente_id = cliente.id
        disp.ultima_vez = ahora

    db.commit()
    return {"ok": True, "nuevo": nuevo, "visitas": cliente.visitas}
