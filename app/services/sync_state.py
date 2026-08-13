"""Control del presupuesto diario de llamadas a la API de datos reales (ver
app/services/football_api.py). El plan gratuito de API-Football permite 100 llamadas/día; este
módulo lleva la cuenta en la tabla `sync_state` para que el backfill histórico se reparta en
varios días sin pasarse del límite, sin importar cuántas veces se reinicie el proceso mientras
tanto (Render free tier duerme y despierta el servicio, lo que reinicia el proceso varias veces
al día)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import SyncState


class BudgetExhausted(Exception):
    pass


class CallBudget:
    """Cuenta llamadas dentro de una sesión de sincronización y persiste el contador en cada
    incremento, para que el progreso sobreviva aunque el proceso se caiga a mitad de camino."""

    def __init__(self, db: Session, max_calls: int) -> None:
        self.db = db
        self.max_calls = max_calls
        self.state = _get_or_create(db)
        if self.state.last_run_date != dt.date.today():
            self.state.last_run_date = dt.date.today()
            self.state.calls_used_today = 0
            db.commit()

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.state.calls_used_today)

    def use(self, n: int = 1) -> None:
        if self.remaining < n:
            raise BudgetExhausted(
                f"Presupuesto diario agotado ({self.state.calls_used_today}/{self.max_calls})."
            )
        self.state.calls_used_today += n
        self.db.commit()


def _get_or_create(db: Session) -> SyncState:
    state = db.get(SyncState, 1)
    if state is None:
        state = SyncState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def mark_teams_synced(db: Session) -> None:
    state = _get_or_create(db)
    state.teams_synced = True
    db.commit()


def mark_fixtures_synced(db: Session) -> None:
    state = _get_or_create(db)
    state.fixtures_synced = True
    db.commit()
