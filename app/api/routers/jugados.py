from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Match, MatchStatus
from app.schemas.match import PlayedMatchOut
from app.services.prediction_service import get_or_create_prediction

router = APIRouter(prefix="/partidos", tags=["Partidos Jugados"])


def _result_sign(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _predicted_sign(prob_home: float, prob_draw: float, prob_away: float) -> str:
    best = max(prob_home, prob_draw, prob_away)
    if best == prob_home:
        return "H"
    if best == prob_away:
        return "A"
    return "D"


@router.get("/jugados", response_model=list[PlayedMatchOut])
def listar_partidos_jugados(
    matchday: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[PlayedMatchOut]:
    """Histórico post-match: Resultado Real vs. Proyectado (Goles, Córners, Tarjetas), con el
    error absoluto de cada mercado — la base para auditar el margen de acierto del motor."""
    stmt = (
        select(Match)
        .where(Match.status == MatchStatus.FINISHED)
        .order_by(Match.kickoff.desc())
    )
    if matchday is not None:
        stmt = stmt.where(Match.matchday == matchday)
    stmt = stmt.limit(limit)

    matches = db.execute(stmt).scalars().all()

    out = []
    for match in matches:
        prediction = get_or_create_prediction(db, match)
        real_sign = _result_sign(match.home_goals, match.away_goals)
        pred_sign = _predicted_sign(prediction.prob_home_win, prediction.prob_draw, prediction.prob_away_win)

        stats_available = match.stats_synced and match.home_corners is not None
        corners_error = None
        cards_error = None
        if stats_available:
            corners_error = abs((match.home_corners + match.away_corners)
                                 - (prediction.expected_home_corners + prediction.expected_away_corners))
            cards_error = abs(
                (match.home_yellow_cards + match.away_yellow_cards + match.home_red_cards + match.away_red_cards)
                - (prediction.expected_home_cards + prediction.expected_away_cards)
            )

        out.append(PlayedMatchOut(
            id=match.id, matchday=match.matchday, kickoff=match.kickoff,
            home_team=match.home_team, away_team=match.away_team,
            real_home_goals=match.home_goals, real_away_goals=match.away_goals,
            real_home_corners=match.home_corners, real_away_corners=match.away_corners,
            real_home_yellow_cards=match.home_yellow_cards, real_away_yellow_cards=match.away_yellow_cards,
            real_home_red_cards=match.home_red_cards, real_away_red_cards=match.away_red_cards,
            stats_available=stats_available,
            projected_home_goals=prediction.expected_home_goals, projected_away_goals=prediction.expected_away_goals,
            projected_home_corners=prediction.expected_home_corners, projected_away_corners=prediction.expected_away_corners,
            projected_total_cards=prediction.expected_home_cards + prediction.expected_away_cards,
            goals_error_abs=abs((match.home_goals + match.away_goals)
                                 - (prediction.expected_home_goals + prediction.expected_away_goals)),
            corners_error_abs=corners_error,
            cards_error_abs=cards_error,
            result_hit=real_sign == pred_sign,
        ))
    db.commit()
    return out
