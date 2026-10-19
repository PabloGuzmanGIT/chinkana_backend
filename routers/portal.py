"""Rutas públicas: las usa el celular del cliente (antes de tener internet) y el login.html del MikroTik."""
import io
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import LOCAL_ID
from config import ahora as hora_local
from db import get_db
from models import Cliente, Dispositivo, Evento
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
    return {"ok": True, "hora": hora_local().isoformat(timespec="seconds")}


@router.get("/ping.png")
def ping():
    return Response(PING_PNG, media_type="image/png", headers=SIN_CACHE)


@router.get("/api/landing")
def get_landing(db: Session = Depends(get_db)):
    return landing.construir(db)


class Registro(BaseModel):
    telefono: str
    acepta_promos: bool          # casilla "Quiero las promos del día por WhatsApp" (opcional para navegar)
    mac: str | None = None
    origen: str = "portal"       # portal (antes de conectarse) | listo (ya conectado)


@router.post("/api/portal/registro")
def registro(datos: Registro, db: Session = Depends(get_db)):
    """Guarda el WhatsApp de quien pidió promos. No abre la sesión: eso lo hace el navegador contra el MikroTik.

    Navegar no exige el número; solo llega aquí quien marcó la casilla de promos (Ley 29733)."""
    if not datos.acepta_promos:
        raise HTTPException(400, "Marca la casilla de promociones para guardar tu WhatsApp.")
    cel = re.sub(r"\D", "", datos.telefono)
    if len(cel) == 11 and cel.startswith("51"):
        cel = cel[2:]
    if not RE_CEL.match(cel):
        raise HTTPException(400, "Ingresa un celular de 9 dígitos que empiece con 9.")
    telefono = "51" + cel
    ahora = hora_local()

    cliente = db.scalar(select(Cliente).where(Cliente.local_id == LOCAL_ID, Cliente.telefono == telefono))
    nuevo = cliente is None
    if nuevo:
        cliente = Cliente(local_id=LOCAL_ID, telefono=telefono, creado=ahora, visitas=0)
        db.add(cliente)
    cliente.visitas += 1
    cliente.ultima_visita = ahora
    cliente.acepto_terminos = ahora      # momento del consentimiento para recibir promos
    db.flush()

    mac = (datos.mac or "").upper()
    if RE_MAC.match(mac):
        disp = db.scalar(select(Dispositivo).where(Dispositivo.local_id == LOCAL_ID, Dispositivo.mac == mac))
        if not disp:
            disp = Dispositivo(local_id=LOCAL_ID, mac=mac, primera_vez=ahora)
            db.add(disp)
        disp.cliente_id = cliente.id
        disp.ultima_vez = ahora

    db.add(Evento(local_id=LOCAL_ID, tipo="wa_suscripcion", ref=datos.origen[:20], fecha=ahora))
    db.commit()
    return {"ok": True, "nuevo": nuevo, "visitas": cliente.visitas}


# Lo que el portal puede registrar. La suscripción a WhatsApp la registra /registro (con consentimiento).
TIPOS_EVENTO = {"portal_visita", "conexion_intento", "conexion", "promo_click", "menu_visita", "contenido_click"}


class EventoIn(BaseModel):
    tipo: str
    ref: str = ""


@router.post("/api/portal/evento", status_code=204)
def evento(datos: EventoIn, db: Session = Depends(get_db)):
    """Analítica anónima: solo el tipo, a qué se refiere y la hora."""
    if datos.tipo not in TIPOS_EVENTO:
        raise HTTPException(400, "Evento desconocido.")
    db.add(Evento(local_id=LOCAL_ID, tipo=datos.tipo, ref=datos.ref[:60]))
    db.commit()
