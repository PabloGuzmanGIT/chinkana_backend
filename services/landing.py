"""Arma todo lo que muestra la landing en una sola respuesta."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import LOCAL_ID, ahora
from models import Categoria, Contenido, Flyer, Producto, Promo
from services import ajustes, clima

MAX_PROMO = 6


SECCIONES = ("sabores", "turismo", "marcas", "novedades")


def momento_del_dia(cfg: dict[str, str] | None = None) -> str:
    cfg = cfg or ajustes.DEFAULTS
    h = ahora().hour
    if h < ajustes.numero(cfg, "hora_almuerzo"):
        return "manana"
    if h < ajustes.numero(cfg, "hora_cafe"):
        return "almuerzo"
    return "cafe" if h < ajustes.numero(cfg, "hora_noche") else "noche"


def contenido_dict(c: Contenido) -> dict:
    return {"id": c.id, "seccion": c.seccion, "titulo": c.titulo, "resumen": c.resumen,
            "imagen": f"/media/contenidos/{c.imagen}" if c.imagen else None, "url": c.url, "activo": c.activo, "orden": c.orden}


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
        "disponible": p.disponible,
        "origen": "pos" if p.externo_id else "local",
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


def _promo(db: Session, productos: list[Producto], clima_hoy: dict | None, cfg: dict[str, str]) -> dict:
    manual = db.scalars(
        select(Promo).where(Promo.local_id == LOCAL_ID, Promo.fecha == ahora().date(), Promo.activa)
        .order_by(Promo.id.desc())
    ).first()
    if manual:
        por_id = {p.id: p for p in productos}
        elegidos = [por_id[i] for i in manual.producto_ids or [] if i in por_id]
        return {"tipo": "manual", "momento": None, "titulo": manual.titulo, "texto": manual.texto,
                "productos": [producto_dict(p) for p in elegidos[:MAX_PROMO]]}

    destacados_primero = sorted(productos, key=lambda p: (not p.destacado, p.orden))
    m = clima_hoy["modo"] if clima_hoy else None
    # El clima extremo gana; en templado o sin datos manda el horario. Mismas reglas que chinkana/login.html.
    momento = m if m in ("frio", "calor") else momento_del_dia(cfg)
    if momento == "calor":
        elegidos = [p for p in destacados_primero if p.temperatura == "fria"]
        titulo, texto = f"Hoy hace {clima_hoy['temp']} °C, ¡refréscate!", "Frappés, bubble tea y bebidas heladas."
    elif momento == "frio":
        elegidos = [p for p in destacados_primero if p.temperatura == "caliente"]
        titulo, texto = f"Hoy hace {clima_hoy['temp']} °C, ¡caliéntate!", "Nuestras bebidas calientes para este frío."
    elif momento == "manana":
        elegidos = [p for p in destacados_primero if p.temperatura == "caliente"]
        titulo, texto = "Empieza el día con un buen café", "Espresso, latte o capuchino recién hechos."
    elif momento == "cafe":
        # "algo dulce": los productos 'ambas' son postres y chocolates en tableta
        elegidos = [p for p in destacados_primero if p.temperatura in ("caliente", "ambas")]
        elegidos.sort(key=lambda p: (not (p.destacado or p.temperatura == "ambas"), p.orden))
        titulo, texto = "Un buen café, algo dulce y un momento para ti", "Café, postres y chocolate de la casa."
    elif momento == "noche":
        elegidos = [p for p in destacados_primero if p.temperatura in ("caliente", "ambas")]
        titulo, texto = "Cierra el día con algo rico", "Chocolate caliente y postres para terminar bien el día."
    else:  # almuerzo: aún no hay platos en la carta, van los destacados
        elegidos = [p for p in destacados_primero if p.destacado]
        titulo, texto = "Tu pausa para recargar energías", "Descubre lo que tenemos para disfrutar algo rico."
    return {"tipo": "clima" if m in ("frio", "calor") else "horario", "momento": momento, "titulo": titulo, "texto": texto,
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
        "negocio": {"nombre": cfg["nombre"], "eslogan": cfg["eslogan"], "wifi_minutos": int(ajustes.numero(cfg, "wifi_minutos")),
                    "ciudad": cfg["ciudad"]},
        "clima": clima_hoy,
        "flyers": _flyers(db, clima_hoy),
        # Lo agotado sale en la carta (marcado), pero nunca se promociona.
        "promo": _promo(db, [p for p in productos if p.disponible], clima_hoy, cfg),
        "propio": {
            "titulo": cfg["propio_titulo"],
            "intro": cfg["propio_intro"],
            "items": [
                {"emoji": "☕", "titulo": "Nuestro café", "texto": cfg["propio_cafe"]},
                {"emoji": "🍫", "titulo": "Nuestro chocolate", "texto": cfg["propio_chocolate"]},
            ],
            "productos": [producto_dict(p) for p in productos if p.propio and p.destacado and p.disponible][:4],
        },
        "carta": carta,
        # Solo secciones con tarjetas: no se muestran secciones vacías ni contenido de relleno.
        "contenidos": {s: items for s in SECCIONES if (items := [
            contenido_dict(c) for c in db.scalars(
                select(Contenido).where(Contenido.local_id == LOCAL_ID, Contenido.activo, Contenido.seccion == s)
                .order_by(Contenido.orden, Contenido.id))])},
        "nosotros": {k: cfg[k] for k in ("nosotros_historia", "nosotros_objetivo", "direccion", "horario")},
        "enlaces": {k: cfg[k] for k in ("wa_canal", "instagram", "facebook", "tiktok", "resena_url")},
    }
