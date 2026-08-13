"""Auto-inicialización para despliegues en la nube (Render, etc.), donde no hay una terminal
para correr `seed_db.py`/`train_models.py` a mano antes del primer arranque.

Se ejecuta en el evento `startup` de FastAPI (ver app/api/main.py) y es IDEMPOTENTE:
  - Solo siembra datos sintéticos si la tabla `teams` está vacía (primera vez contra una base
    Postgres nueva). En arranques posteriores del mismo servicio, la base ya tiene datos y este
    paso se salta en milisegundos.
  - Solo (re)entrena los modelos si falta alguno de los artefactos `.joblib` en `models_dir`.
    En Render free tier el disco es efímero entre *deploys* (pero persiste durante el sueño/
    despertar del servicio), así que esto solo cuesta tiempo real justo después de cada deploy.

Puede desactivarse con `ZONAMED_AUTO_BOOTSTRAP=false` si prefieres poblar la base tú mismo.
"""
from __future__ import annotations

import threading
import traceback

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import init_db, session_scope

settings = get_settings()

# Estado de arranque legible desde el endpoint de salud (ver app/api/main.py). Vive en memoria
# del proceso: suficiente para un único servicio web como este (no hay múltiples réplicas).
status: dict = {"stage": "pending", "detail": ""}


def bootstrap_if_needed() -> None:
    init_db()
    status.update(stage="checking", detail="Verificando si hay datos existentes...")

    from app.models import Team  # import diferido: evita ciclos con app.models -> app.core.database

    with session_scope() as db:
        team_count = db.execute(select(func.count()).select_from(Team)).scalar_one()

    if team_count == 0:
        print("[bootstrap] Base de datos vacía: generando datos sintéticos iniciales...")
        status.update(stage="seeding", detail="Generando datos sintéticos (equipos, partidos, jugadores)...")
        from app.scripts import seed_db

        seed_db.run()
    else:
        print(f"[bootstrap] Base de datos ya tiene {team_count} equipos, se omite el seed.")

    marker = settings.models_dir / "xgb_home_goals.joblib"
    if not marker.exists():
        print("[bootstrap] Artefactos de modelo no encontrados: entrenando el ensemble...")
        status.update(stage="training", detail="Entrenando el ensemble (puede tardar varios minutos en la nube)...")
        from app.scripts import train_models

        train_models.run()
    else:
        print("[bootstrap] Artefactos de modelo ya presentes, se omite el entrenamiento.")

    status.update(stage="ready", detail="Listo.")


def bootstrap_in_background() -> None:
    """Corre el bootstrap en un hilo aparte para que uvicorn abra el puerto de inmediato — si se
    corre de forma bloqueante en el evento `startup`, hosts como Render matan el deploy por
    'timeout esperando un puerto abierto' cuando sembrar/entrenar contra una base remota tarda
    más que la ventana de detección de puerto del proveedor."""

    def _run() -> None:
        try:
            bootstrap_if_needed()
        except Exception as exc:  # noqa: BLE001 — se reporta en el endpoint de salud, no se relanza
            status.update(stage="error", detail=f"{exc}")
            traceback.print_exc()

    threading.Thread(target=_run, name="zonamed-bootstrap", daemon=True).start()
