"""Panel del staff: carta, promos, textos y clientes. Todo requiere sesión (Authorization: Bearer <token>)."""
import csv
import math
import io
import secrets
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from config import LOCAL_ID, MEDIA_DIR, ahora
from db import get_db
from models import Categoria, Cliente, Contenido, Evento, Flyer, Producto, Promo, Staff
from security import crear_token, staff_actual, verificar_clave
from services import ajustes, catalogo, clima
from services.landing import contenido_dict, flyer_dict, producto_dict

router = APIRouter(prefix="/api/admin")
FOTOS_DIR = MEDIA_DIR / "productos"


# ------------------------------------------------------------------ sesión
class Login(BaseModel):
    usuario: str
    clave: str


# El /admin queda en internet: tras 5 claves erradas en 10 min desde la misma IP, se espera.
MAX_FALLOS = 5
VENTANA_SEG = 600
FALLOS: dict[str, list[float]] = {}


def _ip(request: Request) -> str:
    # Detrás del proxy de Railway la IP real es la última de X-Forwarded-For (la que agrega el proxy, no el cliente).
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        return reenviada.split(",")[-1].strip()
    return request.client.host if request.client else "?"


@router.post("/login")
def login(datos: Login, request: Request, db: Session = Depends(get_db)):
    ip, t = _ip(request), time.time()
    recientes = [f for f in FALLOS.get(ip, []) if t - f < VENTANA_SEG]
    if len(recientes) >= MAX_FALLOS:
        espera = math.ceil(VENTANA_SEG - (t - recientes[0]))
        raise HTTPException(429, f"Demasiados intentos. Prueba en {math.ceil(espera / 60)} min.", headers={"Retry-After": str(espera)})

    staff = db.scalar(select(Staff).where(Staff.local_id == LOCAL_ID, Staff.usuario == datos.usuario.strip()))
    if not staff or not staff.activo or not verificar_clave(datos.clave, staff.clave_hash):
        FALLOS[ip] = recientes + [t]
        raise HTTPException(401, "Usuario o clave incorrectos.")
    FALLOS.pop(ip, None)
    return {"token": crear_token(staff.id), "nombre": staff.nombre, "rol": staff.rol}


@router.get("/me")
def me(staff: Staff = Depends(staff_actual)):
    return {"usuario": staff.usuario, "nombre": staff.nombre, "rol": staff.rol}


# ------------------------------------------------------------------ categorías
class CategoriaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    emoji: str = Field("", max_length=8)
    orden: int = 0


def _categoria(db: Session, cid: int) -> Categoria:
    c = db.get(Categoria, cid)
    if not c or c.local_id != LOCAL_ID:
        raise HTTPException(404, "Categoría no encontrada.")
    return c


@router.get("/categorias")
def listar_categorias(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    cats = db.scalars(select(Categoria).where(Categoria.local_id == LOCAL_ID).order_by(Categoria.orden, Categoria.id))
    return [{"id": c.id, "nombre": c.nombre, "emoji": c.emoji, "orden": c.orden} for c in cats]


@router.post("/categorias")
def crear_categoria(datos: CategoriaIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = Categoria(local_id=LOCAL_ID, **datos.model_dump())
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.put("/categorias/{cid}")
def editar_categoria(cid: int, datos: CategoriaIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = _categoria(db, cid)
    for k, v in datos.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/categorias/{cid}")
def borrar_categoria(cid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = _categoria(db, cid)
    if db.scalar(select(func.count()).select_from(Producto).where(Producto.categoria_id == cid)):
        raise HTTPException(400, "La categoría tiene productos. Muévelos o bórralos primero.")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ productos
class ProductoIn(BaseModel):
    categoria_id: int
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = ""
    precio: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    emoji: str = Field("", max_length=8)
    propio: bool = False
    temperatura: Literal["caliente", "fria", "ambas"] = "ambas"
    destacado: bool = False
    activo: bool = True
    orden: int = 0


# Con admintienda, de un producto del POS aquí solo se editan los datos de marketing que el POS no tiene.
CAMPOS_MARKETING = ("emoji", "propio", "temperatura", "destacado", "orden")
DEL_POS = "Esto se cambia en admintienda; aquí se actualiza solo al sincronizar."


def _producto(db: Session, pid: int) -> Producto:
    p = db.get(Producto, pid)
    if not p or p.local_id != LOCAL_ID:
        raise HTTPException(404, "Producto no encontrado.")
    return p


def _no_del_pos(p: Producto) -> None:
    if p.externo_id:
        raise HTTPException(409, DEL_POS)


@router.get("/catalogo")
def estado_catalogo(_: Staff = Depends(staff_actual)):
    return {"configurado": catalogo.configurado(), **catalogo.estado()}


@router.post("/catalogo/sincronizar")
async def sincronizar_catalogo(_: Staff = Depends(staff_actual)):
    if not catalogo.configurado():
        raise HTTPException(400, "Configura ADMINTIENDA_URL y ADMINTIENDA_API_KEY en api/.env y reinicia la API.")
    try:
        await catalogo.sincronizar(completo=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo leer el catálogo de admintienda: {e}")
    return {"configurado": True, **catalogo.estado()}


@router.get("/productos")
def listar_productos(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    prods = db.scalars(select(Producto).where(Producto.local_id == LOCAL_ID).order_by(Producto.categoria_id, Producto.orden, Producto.id))
    return [producto_dict(p) for p in prods]


@router.post("/productos")
def crear_producto(datos: ProductoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    if catalogo.configurado():
        raise HTTPException(409, "Los productos se crean en admintienda; aquí aparecen solos al sincronizar.")
    _categoria(db, datos.categoria_id)
    p = Producto(local_id=LOCAL_ID, **datos.model_dump())
    db.add(p)
    db.commit()
    return producto_dict(p)


@router.put("/productos/{pid}")
def editar_producto(pid: int, datos: ProductoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    p = _producto(db, pid)
    cambios = datos.model_dump()
    if p.externo_id:
        cambios = {k: cambios[k] for k in CAMPOS_MARKETING}
    else:
        _categoria(db, datos.categoria_id)
    for k, v in cambios.items():
        setattr(p, k, v)
    db.commit()
    return producto_dict(p)


@router.delete("/productos/{pid}")
def borrar_producto(pid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    p = _producto(db, pid)
    _no_del_pos(p)
    if p.foto:
        (FOTOS_DIR / p.foto).unlink(missing_ok=True)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/productos/{pid}/foto")
def subir_foto(pid: int, foto: UploadFile = File(...), db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    """Convierte a WebP de máx. 900 px para que la landing cargue rápido en el mini-navegador."""
    p = _producto(db, pid)
    _no_del_pos(p)
    nombre = _guardar_imagen(foto, FOTOS_DIR, str(p.id), 900)
    if p.foto:
        (FOTOS_DIR / p.foto).unlink(missing_ok=True)
    p.foto = nombre
    db.commit()
    return producto_dict(p)


@router.delete("/productos/{pid}/foto")
def quitar_foto(pid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    p = _producto(db, pid)
    _no_del_pos(p)
    if p.foto:
        (FOTOS_DIR / p.foto).unlink(missing_ok=True)
        p.foto = None
        db.commit()
    return producto_dict(p)


# ------------------------------------------------------------------ contenidos (portal de /listo)
CONTENIDOS_DIR = MEDIA_DIR / "contenidos"
Seccion = Literal["sabores", "turismo", "marcas", "novedades"]


class ContenidoIn(BaseModel):
    seccion: Seccion
    titulo: str = Field(min_length=1, max_length=100)
    resumen: str = Field("", max_length=400)
    url: str = Field("", max_length=300, pattern=r"^(https?://\S+)?$")
    activo: bool = True
    orden: int = 0


def _contenido(db: Session, cid: int) -> Contenido:
    c = db.get(Contenido, cid)
    if not c or c.local_id != LOCAL_ID:
        raise HTTPException(404, "Contenido no encontrado.")
    return c


@router.get("/contenidos")
def listar_contenidos(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    filas = db.scalars(select(Contenido).where(Contenido.local_id == LOCAL_ID).order_by(Contenido.seccion, Contenido.orden, Contenido.id))
    return [contenido_dict(c) for c in filas]


@router.post("/contenidos")
def crear_contenido(datos: ContenidoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = Contenido(local_id=LOCAL_ID, **datos.model_dump())
    db.add(c)
    db.commit()
    return contenido_dict(c)


@router.put("/contenidos/{cid}")
def editar_contenido(cid: int, datos: ContenidoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = _contenido(db, cid)
    for k, v in datos.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return contenido_dict(c)


@router.delete("/contenidos/{cid}")
def borrar_contenido(cid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = _contenido(db, cid)
    if c.imagen:
        (CONTENIDOS_DIR / c.imagen).unlink(missing_ok=True)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/contenidos/{cid}/imagen")
def subir_imagen_contenido(cid: int, imagen: UploadFile = File(...), db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    c = _contenido(db, cid)
    nombre = _guardar_imagen(imagen, CONTENIDOS_DIR, f"cont{c.id}", 1080)
    if c.imagen:
        (CONTENIDOS_DIR / c.imagen).unlink(missing_ok=True)
    c.imagen = nombre
    db.commit()
    return contenido_dict(c)


# ------------------------------------------------------------------ métricas (sin datos personales)
@router.get("/metricas")
def metricas(dias: int = 30, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    desde = ahora() - timedelta(days=max(1, min(dias, 365)))
    base = select(Evento.tipo, func.count()).where(Evento.local_id == LOCAL_ID, Evento.fecha >= desde)
    totales = dict(db.execute(base.group_by(Evento.tipo)).all())

    def top(tipo: str) -> list[dict]:
        filas = db.execute(
            select(Evento.ref, func.count().label("n")).where(Evento.local_id == LOCAL_ID, Evento.fecha >= desde, Evento.tipo == tipo)
            .group_by(Evento.ref).order_by(func.count().desc()).limit(10)).all()
        return [{"ref": r, "n": n} for r, n in filas]

    # nombres legibles para los ids de productos y contenidos
    prods = {str(p.id): p.nombre for p in db.scalars(select(Producto).where(Producto.local_id == LOCAL_ID))}
    conts = {f"{c.seccion}:{c.id}": f"{c.seccion} · {c.titulo}" for c in db.scalars(select(Contenido).where(Contenido.local_id == LOCAL_ID))}
    promo = [{**x, "nombre": prods.get(x["ref"], x["ref"])} for x in top("promo_click")]
    contenidos = [{**x, "nombre": conts.get(x["ref"], x["ref"])} for x in top("contenido_click")]
    return {"dias": dias, "totales": totales, "promo": promo, "contenidos": contenidos,
            "suscripciones": top("wa_suscripcion")}


# ------------------------------------------------------------------ flyers
FLYERS_DIR = MEDIA_DIR / "flyers"
ClimaFlyer = Literal["siempre", "frio", "calor"]


def _guardar_imagen(archivo: UploadFile, carpeta, prefijo: str, lado: int) -> str:
    try:
        img = Image.open(archivo.file).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "El archivo no es una imagen válida.")
    img.thumbnail((lado, lado))
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{prefijo}-{secrets.token_hex(4)}.webp"
    img.save(carpeta / nombre, "WEBP", quality=80, method=6)
    return nombre


def _flyer(db: Session, fid: int) -> Flyer:
    f = db.get(Flyer, fid)
    if not f or f.local_id != LOCAL_ID:
        raise HTTPException(404, "Flyer no encontrado.")
    return f


class FlyerIn(BaseModel):
    titulo: str = Field("", max_length=100)
    clima: ClimaFlyer = "siempre"
    producto_id: int | None = None
    activo: bool = True
    orden: int = 0


@router.get("/flyers")
def listar_flyers(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    flyers = db.scalars(select(Flyer).where(Flyer.local_id == LOCAL_ID).order_by(Flyer.orden, Flyer.id))
    return [flyer_dict(f) for f in flyers]


@router.post("/flyers")
def crear_flyer(imagen: UploadFile = File(...), titulo: str = Form(""), clima: ClimaFlyer = Form("siempre"),
                orden: int = Form(0), db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    """Flyers en vertical u horizontal: se guardan en WebP de máx. 1080 px de lado."""
    f = Flyer(local_id=LOCAL_ID, titulo=titulo[:100], clima=clima, orden=orden,
              imagen=_guardar_imagen(imagen, FLYERS_DIR, "flyer", 1080))
    db.add(f)
    db.commit()
    return flyer_dict(f)


@router.put("/flyers/{fid}")
def editar_flyer(fid: int, datos: FlyerIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    f = _flyer(db, fid)
    if datos.producto_id is not None:
        _producto(db, datos.producto_id)
    for k, v in datos.model_dump().items():
        setattr(f, k, v)
    db.commit()
    return flyer_dict(f)


@router.delete("/flyers/{fid}")
def borrar_flyer(fid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    f = _flyer(db, fid)
    (FLYERS_DIR / f.imagen).unlink(missing_ok=True)
    db.delete(f)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ promos
class PromoIn(BaseModel):
    fecha: date
    titulo: str = Field(min_length=1, max_length=100)
    texto: str = ""
    producto_ids: list[int] = []
    activa: bool = True


def _promo_dict(p: Promo) -> dict:
    return {"id": p.id, "fecha": p.fecha.isoformat(), "titulo": p.titulo, "texto": p.texto,
            "producto_ids": p.producto_ids or [], "activa": p.activa}


def _promo(db: Session, pid: int) -> Promo:
    p = db.get(Promo, pid)
    if not p or p.local_id != LOCAL_ID:
        raise HTTPException(404, "Promo no encontrada.")
    return p


@router.get("/promos")
def listar_promos(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    promos = db.scalars(select(Promo).where(Promo.local_id == LOCAL_ID).order_by(Promo.fecha.desc(), Promo.id.desc()).limit(60))
    return [_promo_dict(p) for p in promos]


@router.post("/promos")
def crear_promo(datos: PromoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    p = Promo(local_id=LOCAL_ID, **datos.model_dump())
    db.add(p)
    db.commit()
    return _promo_dict(p)


@router.put("/promos/{pid}")
def editar_promo(pid: int, datos: PromoIn, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    p = _promo(db, pid)
    for k, v in datos.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return _promo_dict(p)


@router.delete("/promos/{pid}")
def borrar_promo(pid: int, db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    db.delete(_promo(db, pid))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ ajustes y clima
@router.get("/ajustes")
def leer_ajustes(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    return ajustes.leer(db)


@router.put("/ajustes")
def guardar_ajustes(cambios: dict[str, str], db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    return ajustes.guardar(db, cambios)


@router.post("/clima/actualizar")
async def actualizar_clima(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    try:
        await clima.actualizar()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo consultar el clima: {e!r}")
    return clima.leer(db, ajustes.leer(db))


# ------------------------------------------------------------------ clientes
def _clientes(db: Session, q: str):
    stmt = select(Cliente).where(Cliente.local_id == LOCAL_ID)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Cliente.telefono.like(like), Cliente.nombre.like(like), Cliente.email.like(like)))
    return db.scalars(stmt.order_by(Cliente.ultima_visita.desc()))


def _cliente_dict(c: Cliente) -> dict:
    return {"id": c.id, "telefono": c.telefono, "nombre": c.nombre, "email": c.email, "visitas": c.visitas,
            "creado": c.creado.isoformat(timespec="minutes"), "ultima_visita": c.ultima_visita.isoformat(timespec="minutes")}


@router.get("/clientes")
def listar_clientes(q: str = "", db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    total = db.scalar(select(func.count()).select_from(Cliente).where(Cliente.local_id == LOCAL_ID))
    return {"total": total, "clientes": [_cliente_dict(c) for c in _clientes(db, q).fetchmany(500)]}


@router.get("/clientes.csv")
def exportar_clientes(db: Session = Depends(get_db), _: Staff = Depends(staff_actual)):
    buf = io.StringIO()
    buf.write("﻿")  # BOM: Excel abre bien las tildes
    w = csv.writer(buf, delimiter=";")
    w.writerow(["telefono", "nombre", "email", "visitas", "primera_visita", "ultima_visita"])
    for c in _clientes(db, ""):
        d = _cliente_dict(c)
        w.writerow([d["telefono"], d["nombre"] or "", d["email"] or "", d["visitas"], d["creado"], d["ultima_visita"]])
    nombre = f"clientes-{ahora().date().isoformat()}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
