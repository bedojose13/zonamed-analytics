from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ScoreProbability(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class OverUnderLine(BaseModel):
    line: float
    prob_over: float
    prob_under: float
    expected_value: float


class MonteCarloMatrix(BaseModel):
    """Salida completa de la simulación Monte Carlo (ver app/predictive/monte_carlo.py).

    `n_simulations` documenta cuántas corridas respaldan la matriz (100,000 por defecto).
    Las distribuciones de córners/tarjetas se exponen truncadas a un rango razonable de
    visualización (0..N) más una cola `+` agregada, para que el frontend no tenga que manejar
    colas infinitas de la Binomial Negativa / Poisson.
    """

    n_simulations: int
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    top_scorelines: list[ScoreProbability]
    total_corners_distribution: dict[str, float]  # "0".."14+" -> prob
    total_cards_distribution: dict[str, float]  # "0".."9+" -> prob
    corner_lines: list[OverUnderLine]
    card_lines: list[OverUnderLine]
    prob_both_teams_score: float
    prob_red_card_shown: float


class PredictionSummaryOut(ORMModel):
    model_version: str
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    expected_home_goals: float
    expected_away_goals: float
    most_likely_score: str

    expected_home_corners: float
    expected_away_corners: float
    corner_line_used: float
    prob_over_corner_line: float

    expected_home_cards: float
    expected_away_cards: float
    expected_total_fouls: float
    card_line_used: float
    prob_over_card_line: float
    prob_red_card_shown: float


class PlayerDisciplineRisk(BaseModel):
    player_id: int
    player_name: str
    team_short_name: str
    card_proneness_index: float
    prob_booked: float = Field(description="Probabilidad estimada de recibir tarjeta en este partido")
