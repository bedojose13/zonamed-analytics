"""Orquestador del pipeline de features: para un partido (histórico o futuro) produce un único
`MatchFeatureSet` con todo lo que consumen los modelos predictivos (Poisson, XGBoost, GLM de
tarjetas, Monte Carlo). Centralizar esto en un solo lugar evita que el entrenamiento y el
servicio de inferencia calculen las features de forma distinta (una fuente de bugs muy común
en sistemas de ML productivos)."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, Referee, Rivalry, Team
from app.services.xcards import (
    compute_team_discipline_rates,
    expected_match_cards,
    expected_match_fouls,
    h2h_intensity_multiplier,
    referee_strictness,
)
from app.services.xg_corners import compute_team_corner_rates, expected_match_corners
from app.services.xg_goals import altitude_fatigue_penalty, compute_team_goal_rates, expected_match_goals


@dataclass
class MatchFeatureSet:
    match_id: int
    home_team_id: int
    away_team_id: int

    expected_home_goals_poisson: float
    expected_away_goals_poisson: float
    expected_home_corners: float
    expected_away_corners: float
    expected_home_fouls: float
    expected_away_fouls: float
    expected_home_cards: float
    expected_away_cards: float

    fatigue_penalty_away: float
    referee_strictness_index: float
    h2h_intensity: float
    is_derby: bool
    venue_altitude_m: float
    altitude_gap_m: float
    temperature_c: float
    humidity_pct: float
    home_rest_days: int
    away_rest_days: int

    def as_ml_row(self) -> dict:
        """Vector plano numérico — el que consume XGBoost (ver app/predictive/xgboost_model.py).
        Todo debe ser conocible ANTES del pitazo inicial (sin fuga de información)."""
        return {
            "expected_home_goals_poisson": self.expected_home_goals_poisson,
            "expected_away_goals_poisson": self.expected_away_goals_poisson,
            "goal_supremacy_poisson": self.expected_home_goals_poisson - self.expected_away_goals_poisson,
            "expected_home_corners": self.expected_home_corners,
            "expected_away_corners": self.expected_away_corners,
            "expected_home_fouls": self.expected_home_fouls,
            "expected_away_fouls": self.expected_away_fouls,
            "expected_home_cards": self.expected_home_cards,
            "expected_away_cards": self.expected_away_cards,
            "fatigue_penalty_away": self.fatigue_penalty_away,
            "referee_strictness_index": self.referee_strictness_index,
            "h2h_intensity": self.h2h_intensity,
            "is_derby": float(self.is_derby),
            "altitude_gap_m": self.altitude_gap_m,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "home_rest_days": self.home_rest_days,
            "away_rest_days": self.away_rest_days,
        }


def _get_rivalry(db: Session, team_a_id: int, team_b_id: int) -> Rivalry | None:
    stmt = select(Rivalry).where(
        ((Rivalry.team_a_id == team_a_id) & (Rivalry.team_b_id == team_b_id))
        | ((Rivalry.team_a_id == team_b_id) & (Rivalry.team_b_id == team_a_id))
    )
    return db.execute(stmt).scalars().first()


def build_feature_set(db: Session, match: Match, *, exclude_this_match: bool = True) -> MatchFeatureSet:
    """Construye las features para `match`. Si `exclude_this_match` es True (default), las
    ventanas de forma reciente se cortan estrictamente antes de este partido — obligatorio
    quando se generan features de entrenamiento sobre partidos históricos, para no filtrar el
    resultado del propio partido dentro de sus propias features."""
    before_id = match.id if exclude_this_match else None

    home_team: Team = match.home_team
    away_team: Team = match.away_team
    referee: Referee | None = match.referee

    home_goal_rates = compute_team_goal_rates(db, home_team.id, before_id)
    away_goal_rates = compute_team_goal_rates(db, away_team.id, before_id)
    home_corner_rates = compute_team_corner_rates(db, home_team.id, before_id)
    away_corner_rates = compute_team_corner_rates(db, away_team.id, before_id)
    home_discipline_rates = compute_team_discipline_rates(db, home_team.id, before_id)
    away_discipline_rates = compute_team_discipline_rates(db, away_team.id, before_id)

    fatigue = altitude_fatigue_penalty(match.venue_altitude_m, away_team.altitude_m, match.away_rest_days)

    exp_home_goals, exp_away_goals = expected_match_goals(home_goal_rates, away_goal_rates, fatigue)
    exp_home_corners, exp_away_corners = expected_match_corners(home_corner_rates, away_corner_rates, fatigue)
    exp_home_fouls, exp_away_fouls = expected_match_fouls(home_discipline_rates, away_discipline_rates)

    rivalry = _get_rivalry(db, home_team.id, away_team.id)
    h2h_mult = h2h_intensity_multiplier(db, home_team.id, away_team.id, rivalry)
    exp_home_cards, exp_away_cards = expected_match_cards(exp_home_fouls, exp_away_fouls, referee, h2h_mult)

    return MatchFeatureSet(
        match_id=match.id, home_team_id=home_team.id, away_team_id=away_team.id,
        expected_home_goals_poisson=exp_home_goals, expected_away_goals_poisson=exp_away_goals,
        expected_home_corners=exp_home_corners, expected_away_corners=exp_away_corners,
        expected_home_fouls=exp_home_fouls, expected_away_fouls=exp_away_fouls,
        expected_home_cards=exp_home_cards, expected_away_cards=exp_away_cards,
        fatigue_penalty_away=fatigue, referee_strictness_index=referee_strictness(referee),
        h2h_intensity=h2h_mult, is_derby=rivalry is not None,
        venue_altitude_m=match.venue_altitude_m,
        altitude_gap_m=max(0.0, match.venue_altitude_m - away_team.altitude_m),
        temperature_c=match.temperature_c, humidity_pct=match.humidity_pct,
        home_rest_days=match.home_rest_days, away_rest_days=match.away_rest_days,
    )
