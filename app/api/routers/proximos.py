from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Match, MatchStatus
from app.schemas.match import UpcomingMatchOut
from app.schemas.prediction import PredictionSummaryOut
from app.services.prediction_service import get_or_create_prediction
from app.services.team_history import HistoryCache

router = APIRouter(prefix="/partidos", tags=["Próximos Partidos"])


@router.get("/proximos", response_model=list[UpcomingMatchOut])
def listar_proximos_partidos(
    matchday: int | None = Query(None, description="Filtrar por jornada específica"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[UpcomingMatchOut]:
    """Lista de partidos futuros con Ganador estimado, Córners y Tarjetas probables (resumen).

    Nota de producción: en un sistema real esto NO debería generar la predicción on-demand por
    request; un job programado (cron/Celery) correría `get_or_create_prediction` tras cada
    actualización de calendario/alineaciones y este endpoint solo leería. Se deja on-demand
    aquí por simplicidad de demo end-to-end.
    """
    stmt = select(Match).where(Match.status == MatchStatus.SCHEDULED).order_by(Match.kickoff.asc())
    if matchday is not None:
        stmt = stmt.where(Match.matchday == matchday)
    stmt = stmt.limit(limit)

    matches = db.execute(stmt).scalars().all()

    # Un solo HistoryCache para todo el request: evita repetir ~10 consultas por partido contra
    # la base remota cuando hay que generar varias predicciones nuevas de una — ver
    # app/services/team_history.py.
    history = HistoryCache(db)

    out = []
    for match in matches:
        prediction = get_or_create_prediction(db, match, history=history)
        out.append(UpcomingMatchOut(
            id=match.id, matchday=match.matchday, kickoff=match.kickoff, status=match.status,
            home_team=match.home_team, away_team=match.away_team, referee=match.referee,
            prediction=PredictionSummaryOut.model_validate(prediction),
        ))
    db.commit()
    return out
