"""API REST — módulo 4 del brief.

Ejecutar:
    uvicorn app.api.main:app --reload --port 8000

Documentación interactiva autogenerada: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import analisis, jugados, proximos
from app.core import bootstrap
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Analítica y predicción probabilística multi-mercado para la Liga BetPlay Dimayor.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo: en producción restringir al origen exacto del frontend
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(proximos.router)
app.include_router(analisis.router)
app.include_router(jugados.router)


@app.on_event("startup")
def on_startup() -> None:
    # init_db() (CREATE TABLE IF NOT EXISTS) es rápido y se corre aquí mismo para que las tablas
    # existan casi de inmediato; el seed/entrenamiento (lento contra una base remota) se manda a
    # un hilo aparte para no retrasar la apertura del puerto — ver app/core/bootstrap.py.
    init_db()
    if settings.auto_bootstrap:
        bootstrap.bootstrap_in_background()
    else:
        bootstrap.status.update(stage="ready", detail="Auto-bootstrap desactivado.")


@app.get("/", tags=["Salud"])
def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name, "bootstrap": bootstrap.status}


@app.post("/admin/sync", tags=["Admin"])
def trigger_sync(token: str) -> dict:
    """Fuerza una corrida más de sincronización real + reentrenamiento, sin esperar a que el
    servicio se duerma y despierte solo. Pensado para un cron externo gratuito (ver DEPLOY.md)
    que avance el backfill histórico incluso en días sin visitas a la app."""
    if not settings.admin_sync_token or token != settings.admin_sync_token:
        raise HTTPException(status_code=403, detail="Token inválido o ZONAMED_ADMIN_SYNC_TOKEN no configurado.")
    if bootstrap.status.get("stage") in {"syncing", "training"}:
        return {"status": "already_running", "bootstrap": bootstrap.status}
    bootstrap.bootstrap_in_background()
    return {"status": "sync_started", "bootstrap": bootstrap.status}
