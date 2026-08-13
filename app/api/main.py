"""API REST — módulo 4 del brief.

Ejecutar:
    uvicorn app.api.main:app --reload --port 8000

Documentación interactiva autogenerada: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import analisis, jugados, proximos
from app.core.bootstrap import bootstrap_if_needed
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
    if settings.auto_bootstrap:
        bootstrap_if_needed()
    else:
        init_db()


@app.get("/", tags=["Salud"])
def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name}
