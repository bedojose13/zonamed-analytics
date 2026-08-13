from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Match, Rivalry
from app.schemas.common import WeatherContext
from app.schemas.match import DetailedMatchAnalysisOut
from app.schemas.prediction import MonteCarloMatrix, PlayerDisciplineRisk, PredictionSummaryOut
from app.services.player_risk import top_discipline_risks
from app.services.prediction_service import get_or_create_prediction

router = APIRouter(prefix="/partidos", tags=["Análisis Detallado"])


@router.get("/analisis-detallado/{partido_id}", response_model=DetailedMatchAnalysisOut)
def analisis_detallado(
    partido_id: int, refresh: bool = False, db: Session = Depends(get_db),
) -> DetailedMatchAnalysisOut:
    """Radiografía completa pre-match: pronóstico de córners/tarjetas, impacto del árbitro,
    clima/altitud y la matriz íntegra de la simulación Monte Carlo."""
    match = db.get(Match, partido_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Partido {partido_id} no encontrado")

    prediction = get_or_create_prediction(db, match, force_refresh=refresh)

    rivalry = db.query(Rivalry).filter(
        ((Rivalry.team_a_id == match.home_team_id) & (Rivalry.team_b_id == match.away_team_id))
        | ((Rivalry.team_a_id == match.away_team_id) & (Rivalry.team_b_id == match.home_team_id))
    ).first()
    referee_strictness_index = prediction.feature_snapshot.get("referee_strictness_index", 1.0)

    discipline_risks = top_discipline_risks(db, match, referee_strictness_index)
    db.commit()

    return DetailedMatchAnalysisOut(
        id=match.id, matchday=match.matchday, kickoff=match.kickoff, status=match.status,
        home_team=match.home_team, away_team=match.away_team, referee=match.referee,
        weather=WeatherContext(
            venue_altitude_m=match.venue_altitude_m, temperature_c=match.temperature_c,
            humidity_pct=match.humidity_pct, home_rest_days=match.home_rest_days,
            away_rest_days=match.away_rest_days, away_travel_km=match.away_travel_km,
        ),
        prediction=PredictionSummaryOut.model_validate(prediction),
        monte_carlo=MonteCarloMatrix.model_validate(prediction.monte_carlo_matrix),
        discipline_risk_players=[PlayerDisciplineRisk.model_validate(r) for r in discipline_risks],
        is_derby=rivalry is not None,
        rivalry_intensity_index=rivalry.intensity_index if rivalry else 1.0,
    )
