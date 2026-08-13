from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncState(Base):
    """Fila única (id=1) que lleva la cuenta de cuántas llamadas a la API de datos reales se han
    usado HOY, para repartir el backfill histórico en varios días sin pasarse del límite de 100
    llamadas/día del plan gratuito de API-Football. Ver app/services/sync_state.py."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_run_date: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    calls_used_today: Mapped[int] = mapped_column(Integer, default=0)
    teams_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    fixtures_synced: Mapped[bool] = mapped_column(Boolean, default=False)
