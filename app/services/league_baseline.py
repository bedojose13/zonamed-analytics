"""Promedios de liga usados como denominador en el modelo ataque/defensa (app/services/rate_model.py).

Por qué esto NO puede ser una constante fija en el código
------------------------------------------------------------
`expected_rate = league_avg * attack_i * defense_j` solo es correcto si `league_avg` refleja el
promedio REAL de la competición sobre la que se está prediciendo. Un valor hardcodeado que no
coincide con los datos (p. ej. tomado de "fútbol en general" en vez de esta liga y temporada
concretas) sesga sistemáticamente TODAS las predicciones hacia arriba o abajo, incluso si los
factores de ataque/defensa de cada equipo son correctos — es un error de calibración global, no
de modelo. Por eso estos promedios se calculan a partir del propio histórico en base de datos
(`compute_league_averages`) y se recalibran cada vez que se re-entrena (`train_models.py`), en
vez de vivir como números mágicos en los módulos de features.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from joblib import dump, load
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Match, MatchStatus, Referee

settings = get_settings()

# Fallbacks razonables (fútbol profesional en general) usados solo antes del primer entrenamiento,
# cuando todavía no hay histórico suficiente en la base de datos para calcular promedios propios.
_FALLBACK = dict(
    goals_for=1.25, corners_for=4.8, fouls_for=14.5, yellow_per_match=3.8,
)


@dataclass
class LeagueAverages:
    goals_for: float
    corners_for: float
    fouls_for: float
    yellow_per_match: float


def compute_league_averages(db: Session) -> LeagueAverages:
    finished = select(Match).where(Match.status == MatchStatus.FINISHED)
    matches = db.execute(finished).scalars().all()
    if not matches:
        return LeagueAverages(**_FALLBACK)

    n_team_matches = len(matches) * 2
    goals_for = sum(m.home_goals + m.away_goals for m in matches) / n_team_matches
    corners_for = sum(m.home_corners + m.away_corners for m in matches) / n_team_matches
    fouls_for = sum(m.home_fouls + m.away_fouls for m in matches) / n_team_matches

    avg_yellow = db.execute(select(func.avg(Referee.avg_yellow_per_match))).scalar()
    yellow_per_match = float(avg_yellow) if avg_yellow else _FALLBACK["yellow_per_match"]

    return LeagueAverages(
        goals_for=max(goals_for, 0.1), corners_for=max(corners_for, 0.5),
        fouls_for=max(fouls_for, 1.0), yellow_per_match=max(yellow_per_match, 0.5),
    )


def save_league_averages(averages: LeagueAverages) -> None:
    dump(asdict(averages), settings.models_dir / "league_baseline.joblib")


def load_league_averages() -> LeagueAverages:
    path = settings.models_dir / "league_baseline.joblib"
    if not path.exists():
        return LeagueAverages(**_FALLBACK)
    return LeagueAverages(**load(path))
