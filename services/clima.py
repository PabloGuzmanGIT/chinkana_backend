"""Clima de Ayacucho con Open-Meteo (gratis, sin clave).

La consulta la hace la PC cada CLIMA_CADA_MIN en segundo plano y la guarda en clima_cache.
La landing solo lee la caché: nunca espera a internet.
"""
import asyncio
from datetime import datetime, timedelta

import httpx

from config import CLIMA_CADA_MIN, CLIMA_VALIDO_HORAS, LOCAL_ID
from db import SessionLocal
from models import ClimaCache
from services import ajustes

URL = "https://api.open-meteo.com/v1/forecast"


def icono(codigo: int) -> tuple[str, str]:
    """Código WMO → (emoji, descripción)."""
    if codigo == 0:
        return "☀️", "Despejado"
    if codigo <= 3:
        return "⛅", "Parcialmente nublado"
    if codigo in (45, 48):
        return "🌫️", "Neblina"
    if 51 <= codigo <= 67:
        return "🌧️", "Lluvia"
    if 71 <= codigo <= 77:
        return "❄️", "Nieve"
    if 80 <= codigo <= 82:
        return "🌦️", "Chubascos"
    if codigo >= 95:
        return "⛈️", "Tormenta"
    return "☁️", "Nublado"


def modo(temp: float, frio: float, calor: float) -> str:
    if temp <= frio:
        return "frio"
    if temp >= calor:
        return "calor"
    return "templado"


async def actualizar() -> None:
    db = SessionLocal()
    try:
        cfg = ajustes.leer(db)
        params = {"latitude": cfg["lat"], "longitude": cfg["lon"],
                  "current": "temperature_2m,weather_code", "timezone": "America/Lima"}
        async with httpx.AsyncClient(timeout=8) as cli:
            r = await cli.get(URL, params=params)
            r.raise_for_status()
            actual = r.json()["current"]
        fila = db.get(ClimaCache, LOCAL_ID) or ClimaCache(local_id=LOCAL_ID)
        fila.temp = float(actual["temperature_2m"])
        fila.codigo = int(actual["weather_code"])
        fila.actualizado = datetime.now()
        db.merge(fila)
        db.commit()
    finally:
        db.close()


async def bucle() -> None:
    while True:
        try:
            await actualizar()
        except Exception as e:  # noqa: BLE001  sin internet: se reintenta en la próxima vuelta
            print("Clima no disponible:", repr(e))
        await asyncio.sleep(CLIMA_CADA_MIN * 60)


def leer(db, cfg: dict[str, str]) -> dict | None:
    fila = db.get(ClimaCache, LOCAL_ID)
    if not fila or datetime.now() - fila.actualizado > timedelta(hours=CLIMA_VALIDO_HORAS):
        return None
    emoji, desc = icono(fila.codigo)
    return {
        "temp": round(fila.temp),
        "icono": emoji,
        "descripcion": desc,
        "modo": modo(fila.temp, ajustes.numero(cfg, "umbral_frio"), ajustes.numero(cfg, "umbral_calor")),
        "actualizado": fila.actualizado.isoformat(timespec="minutes"),
    }
