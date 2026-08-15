"""Expected Corners (xC): módulo 2 del brief.

xC a favor / en contra
-----------------------
Para cada equipo se calcula, sobre sus últimos `rolling_window_matches` (20) partidos, el
promedio ponderado exponencialmente (ver app/services/weighting.py) de:
  - córners ganados por partido      -> xC_for
  - córners concedidos por partido   -> xC_against

Estimación del partido
-----------------------
xC del equipo local en un enfrentamiento H vs A se estima combinando:
  - el xC_for de H (cuántos córners genera H habitualmente)
  - el xC_against de A (cuántos córners suele conceder A)
usando la combinación multiplicativa ataque/defensa de app/services/rate_model.py contra el
promedio de liga. Se aplica además un ajuste de fatiga por altitud/descanso (el equipo
fatigado sostiene menos presión ofensiva sostenida -> menos córners) — mismo mecanismo que en
la simulación de datos, pero aquí como corrección del *pronóstico*, no de la generación.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MatchCornerStats, MatchStatus, Match
from app.services import rate_model
from app.services.league_baseline import load_league_averages
from app.services.team_history import HistoryCache, get_recent_matches
from app.services.weighting import exponential_weighted_average


@dataclass
class CornerRates:
    xc_for: float
    xc_against: float
    wing_play_index: float


def compute_team_corner_rates(db: Session, team_id: int, before_match_id: int | None = None,
                               history: HistoryCache | None = None) -> CornerRates:
    obs = get_recent_matches(db, team_id, before_match_id=before_match_id, require_full_stats=True, history=history)
    if not obs:
        league_avg = load_league_averages().corners_for
        return CornerRates(league_avg, league_avg, 0.5)

    xc_for = exponential_weighted_average([o.corners_for for o in obs])
    xc_against = exponential_weighted_average([o.corners_against for o in obs])

    if history is not None:
        wing_index = history.wing_play_index(team_id)
    else:
        stmt = (
            select(MatchCornerStats.wing_play_index)
            .join(Match, Match.id == MatchCornerStats.match_id)
            .where(MatchCornerStats.team_id == team_id, Match.status == MatchStatus.FINISHED)
            .order_by(Match.kickoff.desc())
            .limit(10)
        )
        wing_values = [row[0] for row in db.execute(stmt).all()]
        wing_index = sum(wing_values) / len(wing_values) if wing_values else 0.5

    return CornerRates(xc_for=xc_for, xc_against=xc_against, wing_play_index=wing_index)


def expected_match_corners(
    home_rates: CornerRates, away_rates: CornerRates, fatigue_penalty_away: float = 1.0,
) -> tuple[float, float]:
    league_avg = load_league_averages().corners_for
    home_attack = rate_model.attack_factor(home_rates.xc_for, league_avg)
    away_defense = rate_model.defense_factor(away_rates.xc_against, league_avg)
    away_attack = rate_model.attack_factor(away_rates.xc_for, league_avg)
    home_defense = rate_model.defense_factor(home_rates.xc_against, league_avg)

    # El juego por bandas (wing_play_index alto) correlaciona con más centros y, por ende,
    # más córners: se usa como un pequeño multiplicador adicional (+/-15% en los extremos).
    home_wing_boost = 1.0 + 0.15 * (home_rates.wing_play_index - 0.5) * 2
    away_wing_boost = 1.0 + 0.15 * (away_rates.wing_play_index - 0.5) * 2

    expected_home = rate_model.expected_rate(league_avg, home_attack, away_defense) * home_wing_boost
    expected_away = (
        rate_model.expected_rate(league_avg, away_attack, home_defense)
        * away_wing_boost / fatigue_penalty_away
    )
    return float(expected_home), float(expected_away)
