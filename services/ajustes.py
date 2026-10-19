"""Textos y parámetros editables desde /admin. Lo que no está en la BD toma el valor por defecto."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import LOCAL_ID
from models import Ajuste

EJ = " (texto de ejemplo: edítalo en /admin)"

DEFAULTS: dict[str, str] = {
    "nombre": "Chinkana",
    "eslogan": "Café y chocolate de nuestra tierra",
    "wifi_minutos": "40",
    "umbral_frio": "18",
    "umbral_calor": "22",
    # Franjas de la promo por horario (cuando el clima no es extremo): hora en que empieza cada una.
    "hora_almuerzo": "11",
    "hora_cafe": "15",
    "hora_noche": "20",
    "ciudad": "Ayacucho",
    "lat": "-13.16",
    "lon": "-74.22",
    "propio_titulo": "Lo nuestro es propio",
    "propio_intro": "No revendemos: el café y el chocolate que tomas aquí los hacemos nosotros." + EJ,
    "propio_cafe": "Café de altura seleccionado y tostado por nosotros, en pequeños lotes para que llegue fresco a tu taza." + EJ,
    "propio_chocolate": "Chocolate elaborado en casa a partir del cacao, sin atajos: lo molemos y preparamos aquí mismo." + EJ,
    "nosotros_historia": "Chinkana nació en Ayacucho con una idea sencilla: un lugar cálido para tomar algo rico hecho por nosotros." + EJ,
    "nosotros_objetivo": "Que cada taza cuente de dónde viene, apoyando a productores locales." + EJ,
    "direccion": "Ayacucho, Perú",
    "horario": "Lun a Dom · 8:00 a 22:00",
    "wa_canal": "",
    "instagram": "",
    "facebook": "",
    "tiktok": "",
    "resena_url": "",
}


def leer(db: Session) -> dict[str, str]:
    datos = dict(DEFAULTS)
    for a in db.scalars(select(Ajuste).where(Ajuste.local_id == LOCAL_ID)):
        datos[a.clave] = a.valor
    return datos


def guardar(db: Session, cambios: dict[str, str]) -> dict[str, str]:
    for clave, valor in cambios.items():
        if clave not in DEFAULTS:
            continue
        fila = db.get(Ajuste, (LOCAL_ID, clave))
        if fila:
            fila.valor = valor
        else:
            db.add(Ajuste(local_id=LOCAL_ID, clave=clave, valor=valor))
    db.commit()
    return leer(db)


def numero(datos: dict[str, str], clave: str) -> float:
    try:
        return float(datos.get(clave) or DEFAULTS[clave])
    except ValueError:
        return float(DEFAULTS[clave])
