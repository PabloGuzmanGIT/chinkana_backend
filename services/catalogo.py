"""Carta desde admintienda (el POS): ahí se crean los productos y se marcan precio y disponibilidad.

La PC copia el catálogo a su BD cada CATALOGO_CADA_MIN (solo lo que cambió, `updatedSince`) y completo
cada CATALOGO_COMPLETO_HORAS. El portal lee siempre la copia local: si se cae internet o el servidor
de admintienda, la carta sigue saliendo con lo último que se sincronizó.

Las fotos se bajan a media/productos/ porque el cliente todavía no tiene internet cuando ve el portal
(Cloudinary no le cargaría).

En /admin del portal solo se editan los datos de marketing que el POS no tiene:
frío/caliente, destacado, propio, emoji y orden.
"""
import asyncio
import hashlib
import io
import json
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from PIL import Image
from sqlalchemy import select

from config import (ADMINTIENDA_API_KEY, ahora, ADMINTIENDA_SUCURSAL, ADMINTIENDA_URL, CATALOGO_CADA_MIN,
                    CATALOGO_COMPLETO_HORAS, LOCAL_ID, MEDIA_DIR)
from db import SessionLocal
from models import Ajuste, Categoria, Producto

FOTOS_DIR = MEDIA_DIR / "productos"
CLAVE_ESTADO = "catalogo_estado"
POR_PAGINA = 100   # el máximo que acepta admintienda

# Para productos nuevos: se adivina por el nombre y la categoría, y se corrige en /admin si hace falta.
# Primero las frías: "café helado" es frío aunque diga café.
FRIAS = ("frapp", "helad", "fría", "fria", "frío", "frio", "iced", "ice ", "cold", "bubble", "limonad", "jugo",
         "smoothie", "granizad", "shake")
CALIENTES = ("caliente", "espresso", "expreso", "american", "capuch", "cappucc", "latte", "café", "cafe", "infusi",
             " mate", " té ", "ponche")


def configurado() -> bool:
    return bool(ADMINTIENDA_URL and ADMINTIENDA_API_KEY)


def temperatura_por_nombre(nombre: str, categoria: str) -> str:
    texto = f" {nombre} {categoria} ".lower()
    if any(k in texto for k in FRIAS):
        return "fria"
    if any(k in texto for k in CALIENTES):
        return "caliente"
    return "ambas"


def estado() -> dict:
    """Última sincronización: cuándo, cuántos productos y el error si falló."""
    with SessionLocal() as db:
        fila = db.get(Ajuste, (LOCAL_ID, CLAVE_ESTADO))
        try:
            return json.loads(fila.valor) if fila else {}
        except ValueError:
            return {}


def _guardar_estado(**cambios) -> None:
    datos = {**estado(), **cambios}
    with SessionLocal() as db:
        db.merge(Ajuste(local_id=LOCAL_ID, clave=CLAVE_ESTADO, valor=json.dumps(datos)))
        db.commit()


async def _pedir(cli: httpx.AsyncClient, ruta: str, **params) -> dict:
    r = await cli.get(ADMINTIENDA_URL + ruta, params={k: v for k, v in params.items() if v},
                      headers={"X-Api-Key": ADMINTIENDA_API_KEY})
    if r.status_code in (401, 403):
        raise RuntimeError("admintienda rechazó la clave: revisa ADMINTIENDA_API_KEY o que la API del negocio esté habilitada.")
    r.raise_for_status()
    return r.json()


def _url_foto(item: dict) -> str | None:
    img = item.get("image") or {}
    return img.get("large") or img.get("url")


async def _bajar_foto(cli: httpx.AsyncClient, externo_id: str, url: str) -> str:
    """WebP de máx. 900 px, como las fotos que se suben a mano en /admin."""
    # Sin Accept explícito, f_auto de Cloudinary puede mandar AVIF y Pillow no lo abre.
    r = await cli.get(url, headers={"Accept": "image/webp,image/jpeg,image/png"})
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    img.thumbnail((900, 900))
    nombre = f"pos-{externo_id[:8]}-{hashlib.sha1(url.encode()).hexdigest()[:8]}.webp"
    img.save(FOTOS_DIR / nombre, "WEBP", quality=80)
    return nombre


async def sincronizar(completo: bool = False) -> dict:
    if not configurado():
        raise RuntimeError("Falta ADMINTIENDA_URL o ADMINTIENDA_API_KEY en api/.env.")
    try:
        return await _sincronizar(completo)
    except Exception as e:
        _guardar_estado(ok=False, error=str(e) or repr(e), fecha_error=ahora().isoformat(timespec="seconds"))
        raise


async def _sincronizar(completo: bool) -> dict:
    desde = None if completo else estado().get("sincronizado")
    completo = completo or not desde
    items: list[dict] = []
    sincronizado = None

    async with httpx.AsyncClient(timeout=20) as cli:
        pagina = 1
        while True:
            d = await _pedir(cli, "/integrations/catalog", page=pagina, pageSize=POR_PAGINA,
                             updatedSince=desde, branchId=ADMINTIENDA_SUCURSAL)
            items += d["items"]
            # El de la primera página: admintienda lo toma antes de consultar, así nada queda entre dos syncs.
            sincronizado = sincronizado or d["syncedAt"]
            if pagina >= d["totalPages"]:
                break
            pagina += 1

        with SessionLocal() as db:
            fotos_actuales = {p.externo_id: (p.foto_origen, p.foto) for p in db.scalars(
                select(Producto).where(Producto.local_id == LOCAL_ID, Producto.externo_id.is_not(None)))}
        fotos_nuevas: dict[str, str] = {}
        for it in items:
            url = _url_foto(it)
            if url and fotos_actuales.get(it["id"], (None, None))[0] != url:
                try:
                    fotos_nuevas[it["id"]] = await _bajar_foto(cli, it["id"], url)
                except Exception as e:  # noqa: BLE001  sin foto nueva se queda la anterior y se reintenta
                    print(f"No se pudo bajar la foto de {it.get('name')}: {e!r}")

    nuevos = 0
    with SessionLocal() as db:
        cats = {c.nombre.lower(): c for c in db.scalars(select(Categoria).where(Categoria.local_id == LOCAL_ID))}
        prods = {p.externo_id: p for p in db.scalars(
            select(Producto).where(Producto.local_id == LOCAL_ID, Producto.externo_id.is_not(None)))}

        for it in items:
            nombre_cat = ((it.get("category") or "").strip() or "Otros")[:60]
            cat = cats.get(nombre_cat.lower())
            if not cat:
                cat = Categoria(local_id=LOCAL_ID, nombre=nombre_cat, emoji="", orden=len(cats))
                db.add(cat)
                db.flush()
                cats[nombre_cat.lower()] = cat

            p = prods.get(it["id"])
            if not p:
                p = Producto(local_id=LOCAL_ID, externo_id=it["id"], emoji="", propio=False, destacado=False, orden=0,
                             temperatura=temperatura_por_nombre(it["name"], nombre_cat))
                db.add(p)
                prods[it["id"]] = p
                nuevos += 1
            p.categoria_id = cat.id
            p.nombre = it["name"][:80]
            p.descripcion = it.get("description") or ""
            p.precio = Decimal(str(it.get("priceFrom") or 0))
            p.activo = bool(it.get("active"))
            p.disponible = bool(it.get("available"))

            if it["id"] in fotos_nuevas:
                if p.foto and p.foto != fotos_nuevas[it["id"]]:
                    (FOTOS_DIR / p.foto).unlink(missing_ok=True)
                p.foto, p.foto_origen = fotos_nuevas[it["id"]], _url_foto(it)
            elif not _url_foto(it) and p.foto_origen:
                # Le quitaron la foto en el POS
                (FOTOS_DIR / p.foto).unlink(missing_ok=True)
                p.foto = p.foto_origen = None

        if completo:
            # El listado completo trae solo lo activo: lo que no vino se borró o archivó en el POS.
            # Incluye la carta de ejemplo (sin externo_id). Se oculta, no se borra.
            vistos = {it["id"] for it in items}
            for p in db.scalars(select(Producto).where(Producto.local_id == LOCAL_ID, Producto.activo)):
                if p.externo_id not in vistos:
                    p.activo = False
        # Los borrados de verdad en modo incremental (`removed`) llegan por variante; se resuelven en el próximo completo.
        db.commit()

        activos = sum(1 for p in prods.values() if p.activo)

    resumen = {"ok": True, "error": "", "sincronizado": sincronizado, "completo": completo,
               "fecha": ahora().isoformat(timespec="seconds"),
               "cambios": len(items), "nuevos": nuevos, "productos": activos}
    _guardar_estado(**resumen)
    return resumen


async def bucle() -> None:
    if not configurado():
        print("Carta manual: sin ADMINTIENDA_URL / ADMINTIENDA_API_KEY en api/.env.")
        return
    ultimo_completo: datetime | None = None
    while True:
        completo = not ultimo_completo or ahora() - ultimo_completo > timedelta(hours=CATALOGO_COMPLETO_HORAS)
        try:
            await sincronizar(completo)
            if completo:
                ultimo_completo = ahora()
        except Exception as e:  # noqa: BLE001  sin internet o POS caído: se queda la última copia
            print("Catálogo de admintienda no disponible:", repr(e))
        await asyncio.sleep(CATALOGO_CADA_MIN * 60)
