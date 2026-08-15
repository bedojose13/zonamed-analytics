"""Tasas de gol (λ) por equipo — insumo del modelo Poisson Biparamétrico (app/predictive/poisson_1x2.py).

Mismo mecanismo ataque/defensa que xC y xCards, aplicado a goles, más el ajuste de ventaja de
localía y fatiga por altitud/descanso que en fútbol sudamericano es un efecto documentado y
material (equipos de tierra caliente visitando Bogotá/Pasto rinden peor)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services import rate_model
from app.services.league_baseline import load_league_averages
from app.services.team_history import HistoryCache, get_recent_matches
from app.services.weighting import exponential_weighted_average

HOME_ADVANTAGE = 1.12  # multiplicador liga-wide: los locales anotan ~12% más que los visitantes


@dataclass
class GoalRates:
    goals_for: float
    goals_against: float


def compute_team_goal_rates(db: Session, team_id: int, before_match_id: int | None = None,
                             history: HistoryCache | None = None) -> GoalRates:
    obs = get_recent_matches(db, team_id, before_match_id=before_match_id, history=history)
    if not obs:
        league_avg = load_league_averages().goals_for
        return GoalRates(league_avg, league_avg)
    return GoalRates(
        goals_for=exponential_weighted_average([o.goals_for for o in obs]),
        goals_against=exponential_weighted_average([o.goals_against for o in obs]),
    )


def altitude_fatigue_penalty(home_altitude_m: float, away_team_home_altitude_m: float, away_rest_days: int) -> float:
    """>1.0 penaliza (divide) el rendimiento ofensivo del visitante."""
    altitude_gap = max(0.0, home_altitude_m - away_team_home_altitude_m)
    rest_penalty = max(0, (6 - away_rest_days)) * 0.02
    return 1.0 + (altitude_gap / 3000.0) * 0.15 + rest_penalty


def expected_match_goals(
    home_rates: GoalRates, away_rates: GoalRates, fatigue_penalty_away: float = 1.0,
) -> tuple[float, float]:
    league_avg = load_league_averages().goals_for
    home_attack = rate_model.attack_factor(home_rates.goals_for, league_avg)
    away_defense = rate_model.defense_factor(away_rates.goals_against, league_avg)
    away_attack = rate_model.attack_factor(away_rates.goals_for, league_avg)
    home_defense = rate_model.defense_factor(home_rates.goals_against, league_avg)

    expected_home = rate_model.expected_rate(league_avg, home_attack, away_defense) * HOME_ADVANTAGE
    expected_away = rate_model.expected_rate(league_avg, away_attack, home_defense) / fatigue_penalty_away
    return float(expected_home), float(expected_away)
