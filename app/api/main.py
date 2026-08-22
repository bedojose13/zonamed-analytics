"""API REST — módulo 4 del brief.

Ejecutar:
    uvicorn app.api.main:app --reload --port 8000

Documentación interactiva autogenerada: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import analisis, jugados, proximos
from app.core import bootstrap
from app.core.config import get_settings
from app.core.database import init_db
from app.services import espn_api

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

# Diagnóstico temporal: guarda el traceback completo del último error 500 en memoria, expuesto
# vía GET /admin/last-error?token=... — Render (plan free) no da acceso directo a logs desde
# aquí, así que esto es la única forma de ver QUÉ falló en producción cuando algo solo
# reproduce ahí y nunca en local contra la misma base. Quitar una vez diagnosticado.
_last_error: dict = {}


@app.exception_handler(Exception)
async def _capture_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    _last_error["path"] = str(request.url)
    _last_error["traceback"] = traceback.format_exc()
    _last_error["type"] = type(exc).__name__
    _last_error["message"] = str(exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

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
    if bootstrap.status.get("stage") in {"syncing", "training", "predicting"}:
        return {"status": "already_running", "bootstrap": bootstrap.status}
    bootstrap.bootstrap_in_background()
    return {"status": "sync_started", "bootstrap": bootstrap.status}


@app.get("/admin/test-espn", tags=["Admin"])
def test_espn_connectivity(token: str) -> dict:
    """Diagnóstico: ¿el servidor de Render logra conectarse a la API no oficial de ESPN (que sí
    cubre la temporada en curso)? No guarda nada, solo reporta el resultado. Ver
    app/services/espn_api.py."""
    if not settings.admin_sync_token or token != settings.admin_sync_token:
        raise HTTPException(status_code=403, detail="Token inválido.")
    return espn_api.test_connectivity()


@app.get("/admin/last-error", tags=["Admin"])
def last_error(token: str) -> dict:
    """Traceback completo del último error 500 no manejado, capturado en memoria (ver arriba).
    Diagnóstico temporal mientras no haya acceso directo a logs de Render desde aquí."""
    if not settings.admin_sync_token or token != settings.admin_sync_token:
        raise HTTPException(status_code=403, detail="Token inválido.")
    return _last_error or {"message": "Sin errores capturados todavía."}
