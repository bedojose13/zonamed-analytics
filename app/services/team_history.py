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
                        limit: int | None = None) -> list[MatchObservation]:
    """Últimos `limit` partidos FINALIZADOS del equipo, más reciente primero.

    `before_match_id` permite reconstruir el estado "como se sabía en ese momento" al generar
    features para un partido histórico (evita fuga de información / look-ahead bias).
    """
    n = limit or settings.rolling_window_matches
    stmt = (
        select(Match)
        .where(
            Match.status == MatchStatus.FINISHED,
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
        )
        .order_by(Match.kickoff.desc())
    )
    matches = db.execute(stmt).scalars().all()

    observations: list[MatchObservation] = []
    for m in matches:
        if before_match_id is not None and m.id >= before_match_id:
            continue
        is_home = m.home_team_id == team_id
        observations.append(MatchObservation(
            match_id=m.id, kickoff=m.kickoff, is_home=is_home,
            goals_for=m.home_goals if is_home else m.away_goals,
            goals_against=m.away_goals if is_home else m.home_goals,
            corners_for=m.home_corners if is_home else m.away_corners,
            corners_against=m.away_corners if is_home else m.home_corners,
            cards_for=(m.home_yellow_cards + m.home_red_cards) if is_home
            else (m.away_yellow_cards + m.away_red_cards),
            cards_against=(m.away_yellow_cards + m.away_red_cards) if is_home
            else (m.home_yellow_cards + m.home_red_cards),
            fouls_for=m.home_fouls if is_home else m.away_fouls,
            fouls_against=m.away_fouls if is_home else m.home_fouls,
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
