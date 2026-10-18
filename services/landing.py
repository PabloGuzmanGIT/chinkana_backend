"""Arma todo lo que muestra la landing en una sola respuesta."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import LOCAL_ID
from models import Categoria, Flyer, Producto, Promo
from services import ajustes, clima

MAX_PROMO = 6


def producto_dict(p: Producto) -> dict:
    return {
        "id": p.id,
        "categoria_id": p.categoria_id,
        "nombre": p.nombre,
        "descripcion": p.descripcion,
        "precio": float(p.precio),
        "emoji": p.emoji,
        "foto": f"/media/productos/{p.foto}" if p.foto else None,
        "propio": p.propio,
        "temperatura": p.temperatura,
        "destacado": p.destacado,
        "activo": p.activo,
        "orden": p.orden,
    }


def flyer_dict(f: Flyer) -> dict:
    return {"id": f.id, "titulo": f.titulo, "imagen": f"/media/flyers/{f.imagen}", "clima": f.clima,
            "producto_id": f.producto_id, "activo": f.activo, "orden": f.orden}


def _flyers(db: Session, clima_hoy: dict | None) -> list[dict]:
    """Los de 'siempre' más los del clima de hoy (en templado o sin clima, solo 'siempre')."""
    m = clima_hoy["modo"] if clima_hoy else None
    validos = {"siempre", m} if m in ("frio", "calor") else {"siempre"}
    flyers = db.scalars(select(Flyer).where(Flyer.local_id == LOCAL_ID, Flyer.activo).order_by(Flyer.orden, Flyer.id))
    return [flyer_dict(f) for f in flyers if f.clima in validos]


def _promo(db: Session, productos: list[Producto], clima_hoy: dict | None) -> dict:
    manual = db.scalars(
        select(Promo).where(Promo.local_id == LOCAL_ID, Promo.fecha == date.today(), Promo.activa)
        .order_by(Promo.id.desc())
    ).first()
    if manual:
        por_id = {p.id: p for p in productos}
        elegidos = [por_id[i] for i in manual.producto_ids or [] if i in por_id]
        return {"tipo": "manual", "titulo": manual.titulo, "texto": manual.texto,
                "productos": [producto_dict(p) for p in elegidos[:MAX_PROMO]]}

    destacados_primero = sorted(productos, key=lambda p: (not p.destacado, p.orden))
    m = clima_hoy["modo"] if clima_hoy else None
    if m == "frio":
        elegidos = [p for p in destacados_primero if p.temperatura == "caliente"]
        titulo, texto = f"Hoy hace {clima_hoy['temp']} °C, ¡caliéntate!", "Nuestras bebidas calientes para este frío."
    elif m == "calor":
        elegidos = [p for p in destacados_primero if p.temperatura == "fria"]
        titulo, texto = f"Hoy hace {clima_hoy['temp']} °C, ¡refréscate!", "Frappés, bubble tea y bebidas heladas."
    elif m == "templado":
        elegidos = [p for p in destacados_primero if p.destacado]
        titulo, texto = f"Hoy hace {clima_hoy['temp']} °C", "Un clima rico para cualquier antojo."
    else:
        elegidos = [p for p in destacados_primero if p.destacado]
        titulo, texto = "Recomendados de la casa", "Lo que más piden nuestros clientes."
    return {"tipo": "clima" if m else "destacados", "titulo": titulo, "texto": texto,
            "productos": [producto_dict(p) for p in elegidos[:MAX_PROMO]]}


def construir(db: Session) -> dict:
    cfg = ajustes.leer(db)
    clima_hoy = clima.leer(db, cfg)
    categorias = db.scalars(select(Categoria).where(Categoria.local_id == LOCAL_ID).order_by(Categoria.orden, Categoria.id)).all()
    productos = db.scalars(
        select(Producto).where(Producto.local_id == LOCAL_ID, Producto.activo).order_by(Producto.orden, Producto.id)
    ).all()

    carta = []
    for c in categorias:
        items = [producto_dict(p) for p in productos if p.categoria_id == c.id]
        if items:
            carta.append({"id": c.id, "nombre": c.nombre, "emoji": c.emoji, "productos": items})

    return {
        "negocio": {"nombre": cfg["nombre"], "eslogan": cfg["eslogan"], "wifi_minutos": int(ajustes.numero(cfg, "wifi_minutos"))},
        "clima": clima_hoy,
        "flyers": _flyers(db, clima_hoy),
        "promo": _promo(db, list(productos), clima_hoy),
        "propio": {
            "titulo": cfg["propio_titulo"],
            "intro": cfg["propio_intro"],
            "items": [
                {"emoji": "☕", "titulo": "Nuestro café", "texto": cfg["propio_cafe"]},
                {"emoji": "🍫", "titulo": "Nuestro chocolate", "texto": cfg["propio_chocolate"]},
            ],
            "productos": [producto_dict(p) for p in productos if p.propio and p.destacado][:4],
        },
        "carta": carta,
        "nosotros": {k: cfg[k] for k in ("nosotros_historia", "nosotros_objetivo", "direccion", "horario")},
        "enlaces": {k: cfg[k] for k in ("wa_canal", "instagram", "facebook", "tiktok", "resena_url")},
    }
