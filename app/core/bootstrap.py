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

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import init_db, session_scope

settings = get_settings()


def bootstrap_if_needed() -> None:
    init_db()

    from app.models import Team  # import diferido: evita ciclos con app.models -> app.core.database

    with session_scope() as db:
        team_count = db.execute(select(func.count()).select_from(Team)).scalar_one()

    if team_count == 0:
        print("[bootstrap] Base de datos vacía: generando datos sintéticos iniciales...")
        from app.scripts import seed_db

        seed_db.run()
    else:
        print(f"[bootstrap] Base de datos ya tiene {team_count} equipos, se omite el seed.")

    marker = settings.models_dir / "xgb_home_goals.joblib"
    if not marker.exists():
        print("[bootstrap] Artefactos de modelo no encontrados: entrenando el ensemble...")
        from app.scripts import train_models

        train_models.run()
    else:
        print("[bootstrap] Artefactos de modelo ya presentes, se omite el entrenamiento.")
