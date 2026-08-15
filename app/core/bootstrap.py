"""Auto-inicialización para despliegues en la nube (Render, etc.), donde no hay una terminal
para correr los scripts a mano antes del primer arranque.

Se ejecuta en el evento `startup` de FastAPI (ver app/api/main.py) y es IDEMPOTENTE Y
RESUMIBLE:
  - `sync_highlightly.run()` SIEMPRE se corre: re-trae el calendario completo (barato, ~4
    llamadas) para mantener resultados/estados al día, y cada corrida avanza un poco más el
    backfill de estadísticas por partido (córners/faltas/tarjetas), respetando el cupo diario
    de 100 llamadas del plan gratuito — ver app/services/sync_state.py. Como el free tier de
    Render reinicia el proceso cada vez que el servicio despierta de dormir, esto hace que el
    backfill avance solo con el tráfico normal, sin necesitar un cron aparte (aunque también se
    puede forzar vía POST /admin/sync, ver app/api/main.py).
  - El (re)entrenamiento de modelos también se corre siempre: es barato (no llama a la API
    externa) y así los modelos de córners/tarjetas van mejorando día a día conforme el backfill
    avanza, en vez de quedar congelados con el primer entrenamiento.

Puede desactivarse con `ZONAMED_AUTO_BOOTSTRAP=false` si prefieres correr los scripts tú mismo.
"""
from __future__ import annotations

import threading
import traceback

from app.core.database import init_db

# Estado de arranque legible desde el endpoint de salud (ver app/api/main.py). Vive en memoria
# del proceso: suficiente para un único servicio web como este (no hay múltiples réplicas).
status: dict = {"stage": "pending", "detail": ""}


def bootstrap_if_needed() -> None:
    init_db()

    status.update(stage="syncing", detail="Sincronizando datos reales (Highlightly, temporada en curso)...")
    print("[bootstrap] Sincronizando datos reales...")
    from app.scripts import sync_highlightly

    sync_highlightly.run()

    status.update(stage="training", detail="Entrenando/recalibrando el ensemble...")
    print("[bootstrap] Entrenando el ensemble...")
    from app.scripts import train_models

    train_models.run()

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
