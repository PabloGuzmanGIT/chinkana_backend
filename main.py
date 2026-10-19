"""
Chinkana WiFi — API (FastAPI)

Desarrollo:  uvicorn main:app --reload --port 8000   (el front corre aparte en :3000)
Producción:  además sirve el front ya compilado (web/out) en el mismo puerto.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import seed
from config import CORS_ORIGINS, MEDIA_DIR, WEB_DIR
from routers import admin, portal
from services import catalogo, clima


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed.iniciar()
    tareas = [asyncio.create_task(clima.bucle()), asyncio.create_task(catalogo.bucle())]
    yield
    for t in tareas:
        t.cancel()


app = FastAPI(title="Chinkana WiFi", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

app.include_router(portal.router)
app.include_router(admin.router)

for sub in ("productos", "flyers", "contenidos"):
    (MEDIA_DIR / sub).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

if WEB_DIR.is_dir():
    @app.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/portal/")

    # Debe ir al final: todo lo que no sea /api, /media o /ping.png es el front estático.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
else:
    print(f"Front no compilado ({WEB_DIR}). Usa 'npm run dev' en web/ o 'npm run build'.")
