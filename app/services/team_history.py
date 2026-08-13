"""Acceso a la ventana de forma reciente de un equipo (últimos N partidos jugados)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Match, MatchStatus

settings = get_settings()


@dataclass
class MatchObservation:
    """Una fila 'desde la perspectiva del equipo': for/against ya orientados sin importar si
    el equipo jugó de local o visitante."""

    match_id: int
    kickoff: object
    is_home: bool
    goals_for: int
    goals_against: int
    corners_for: int
    corners_against: int
    cards_for: int  # amarillas + rojas propias
    cards_against: int
    fouls_for: int
    fouls_against: int
    opponent_id: int


def get_recent_matches(db: Session, team_id: int, before_match_id: int | None = None,
                        limit: int | None = None, require_full_stats: bool = False) -> list[MatchObservation]:
    """Últimos `limit` partidos FINALIZADOS del equipo, más reciente primero.

    `before_match_id` permite reconstruir el estado "como se sabía en ese momento" al generar
    features para un partido histórico (evita fuga de información / look-ahead bias).

    `require_full_stats`: con datos reales, el resultado (goles) de un partido FINISHED se
    conoce siempre, pero córners/faltas/tarjetas solo llegan después del backfill incremental
    por partido (ver app/scripts/sync_real_data.py, limitado por el cupo diario de la API). Los
    módulos de córners/tarjetas deben pasar `True` aquí para no mezclar partidos sin ese dato
    todavía (evita reventar el promedio con `None`); el módulo de goles usa el default `False`.
    """
    n = limit or settings.rolling_window_matches
    conditions = [
        Match.status == MatchStatus.FINISHED,
        (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
    ]
    if require_full_stats:
        conditions.append(Match.stats_synced.is_(True))
    stmt = select(Match).where(*conditions).order_by(Match.kickoff.desc())
    matches = db.execute(stmt).scalars().all()

    observations: list[MatchObservation] = []
    for m in matches:
        if before_match_id is not None and m.id >= before_match_id:
            continue
        is_home = m.home_team_id == team_id
        # córners/faltas/tarjetas pueden ser None (partido FINISHED cuyo backfill de estadísticas
        # todavía no llega, ver Match.stats_synced): se usa 0 como relleno seguro aquí porque solo
        # se consumen de verdad cuando require_full_stats=True filtró de antemano esos partidos.
        home_yellow, away_yellow = m.home_yellow_cards or 0, m.away_yellow_cards or 0
        home_red, away_red = m.home_red_cards or 0, m.away_red_cards or 0
        observations.append(MatchObservation(
            match_id=m.id, kickoff=m.kickoff, is_home=is_home,
            goals_for=m.home_goals if is_home else m.away_goals,
            goals_against=m.away_goals if is_home else m.home_goals,
            corners_for=(m.home_corners if is_home else m.away_corners) or 0,
            corners_against=(m.away_corners if is_home else m.home_corners) or 0,
            cards_for=(home_yellow + home_red) if is_home else (away_yellow + away_red),
            cards_against=(away_yellow + away_red) if is_home else (home_yellow + home_red),
            fouls_for=(m.home_fouls if is_home else m.away_fouls) or 0,
            fouls_against=(m.away_fouls if is_home else m.home_fouls) or 0,
            opponent_id=m.away_team_id if is_home else m.home_team_id,
        ))
        if len(observations) >= n:
            break
    return observations


def get_h2h_matches(db: Session, team_a_id: int, team_b_id: int, limit: int = 6) -> list[Match]:
    stmt = (
        select(Match)
        .where(
            Match.status == MatchStatus.FINISHED,
            (
                ((Match.home_team_id == team_a_id) & (Match.away_team_id == team_b_id))
                | ((Match.home_team_id == team_b_id) & (Match.away_team_id == team_a_id))
            ),
        )
        .order_by(Match.kickoff.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
