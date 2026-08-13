from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.models.enums import MatchStatus
from app.schemas.common import RefereeOut, TeamOut, WeatherContext
from app.schemas.prediction import MonteCarloMatrix, PlayerDisciplineRisk, PredictionSummaryOut


class UpcomingMatchOut(BaseModel):
    """GET /partidos/proximos — una fila por partido futuro con el pronóstico resumido."""

    id: int
    matchday: int
    kickoff: dt.datetime
    status: MatchStatus
    home_team: TeamOut
    away_team: TeamOut
    referee: RefereeOut | None
    prediction: PredictionSummaryOut | None  # None si aún no se ha corrido el motor para este partido


class DetailedMatchAnalysisOut(BaseModel):
    """GET /partidos/analisis-detallado/{partido_id} — radiografía completa pre-match."""

    id: int
    matchday: int
    kickoff: dt.datetime
    status: MatchStatus
    home_team: TeamOut
    away_team: TeamOut
    referee: RefereeOut | None
    weather: WeatherContext
    prediction: PredictionSummaryOut
    monte_carlo: MonteCarloMatrix
    discipline_risk_players: list[PlayerDisciplineRisk]
    is_derby: bool
    rivalry_intensity_index: float


class PlayedMatchOut(BaseModel):
    """GET /partidos/jugados — histórico: real vs. proyectado, con el error de predicción."""

    id: int
    matchday: int
    kickoff: dt.datetime
    home_team: TeamOut
    away_team: TeamOut

    real_home_goals: int
    real_away_goals: int
    real_home_corners: int
    real_away_corners: int
    real_home_yellow_cards: int
    real_away_yellow_cards: int
    real_home_red_cards: int
    real_away_red_cards: int

    projected_home_goals: float
    projected_away_goals: float
    projected_home_corners: float
    projected_away_corners: float
    projected_total_cards: float

    goals_error_abs: float
    corners_error_abs: float
    cards_error_abs: float
    result_hit: bool  # ¿el signo 1X2 más probable coincidió con el resultado real?
