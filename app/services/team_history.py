"""Acceso a la ventana de forma reciente de un equipo (últimos N partidos jugados)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Match, MatchCornerStats, MatchStatus

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


def _to_observation(m: Match, team_id: int) -> MatchObservation:
    is_home = m.home_team_id == team_id
    # córners/faltas/tarjetas pueden ser None (partido FINISHED cuyo backfill de estadísticas
    # todavía no llega, ver Match.stats_synced): se usa 0 como relleno seguro aquí porque solo
    # se consumen de verdad cuando require_full_stats=True filtró de antemano esos partidos.
    home_yellow, away_yellow = m.home_yellow_cards or 0, m.away_yellow_cards or 0
    home_red, away_red = m.home_red_cards or 0, m.away_red_cards or 0
    return MatchObservation(
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
    )


class HistoryCache:
    """Precarga TODO el historial de partidos FINALIZADOS en una sola consulta y responde
    `recent_matches`/`h2h_matches` en memoria, sin volver a tocar la base.

    Por qué existe
    ----------------
    `build_feature_set` llama a `get_recent_matches`/`get_h2h_matches` varias veces POR
    PARTIDO (una vez por equipo y por mercado: goles, córners, faltas). Entrenar sobre el
    historial completo (ver app/scripts/train_models.py) implica llamar a `build_feature_set`
    una vez POR CADA partido histórico — con cientos de partidos reales eso son miles de
    consultas individuales. Contra una base remota con latencia de red real (Neon en otra
    región que el servidor), esas miles de idas y vueltas son la diferencia entre segundos y
    varios minutos. Esta clase convierte ese patrón N+1 en una sola consulta inicial.

    Para servir UNA predicción en vivo (un solo partido) esto no hace falta — por eso todas las
    funciones de este módulo lo reciben como parámetro OPCIONAL (`history=None` por defecto) y
    caen de vuelta a consultar la base directamente cuando no se pasa.
    """

    def __init__(self, db: Session) -> None:
        stmt = select(Match).where(Match.status == MatchStatus.FINISHED).order_by(Match.kickoff.desc())
        matches = list(db.execute(stmt).scalars().all())
        self._by_team: dict[int, list[Match]] = defaultdict(list)
        for m in matches:
            self._by_team[m.home_team_id].append(m)
            self._by_team[m.away_team_id].append(m)
        # cada lista ya queda ordenada desc (se recorrió `matches`, que ya viene desc)

        wing_stmt = (
            select(MatchCornerStats.team_id, MatchCornerStats.wing_play_index, Match.kickoff)
            .join(Match, Match.id == MatchCornerStats.match_id)
            .where(Match.status == MatchStatus.FINISHED)
            .order_by(Match.kickoff.desc())
        )
        self._wing_by_team: dict[int, list[float]] = defaultdict(list)
        for team_id, wing_play_index, _ in db.execute(wing_stmt).all():
            self._wing_by_team[team_id].append(wing_play_index)

    def recent_matches(self, team_id: int, before_match_id: int | None = None,
                        limit: int | None = None, require_full_stats: bool = False) -> list[MatchObservation]:
        n = limit or settings.rolling_window_matches
        observations: list[MatchObservation] = []
        for m in self._by_team.get(team_id, []):
            if before_match_id is not None and m.id >= before_match_id:
                continue
            if require_full_stats and not m.stats_synced:
                continue
            observations.append(_to_observation(m, team_id))
            if len(observations) >= n:
                break
        return observations

    def h2h_matches(self, team_a_id: int, team_b_id: int, limit: int = 6) -> list[Match]:
        result = [m for m in self._by_team.get(team_a_id, [])
                  if m.home_team_id == team_b_id or m.away_team_id == team_b_id]
        return result[:limit]

    def wing_play_index(self, team_id: int, limit: int = 10) -> float:
        values = self._wing_by_team.get(team_id, [])[:limit]
        return sum(values) / len(values) if values else 0.5


def get_recent_matches(db: Session, team_id: int, before_match_id: int | None = None,
                        limit: int | None = None, require_full_stats: bool = False,
                        history: HistoryCache | None = None) -> list[MatchObservation]:
    """Últimos `limit` partidos FINALIZADOS del equipo, más reciente primero.

    `before_match_id` permite reconstruir el estado "como se sabía en ese momento" al generar
    features para un partido histórico (evita fuga de información / look-ahead bias).

    `require_full_stats`: con datos reales, el resultado (goles) de un partido FINISHED se
    conoce siempre, pero córners/faltas/tarjetas solo llegan después del backfill incremental
    por partido (ver app/scripts/sync_real_data.py, limitado por el cupo diario de la API). Los
    módulos de córners/tarjetas deben pasar `True` aquí para no mezclar partidos sin ese dato
    todavía (evita reventar el promedio con `None`); el módulo de goles usa el default `False`.

    `history`: si se pasa un `HistoryCache` ya construido (ver arriba), se usa en vez de
    consultar la base — así se evita repetir la misma consulta cientos de veces al entrenar.
    """
    if history is not None:
        return history.recent_matches(team_id, before_match_id, limit, require_full_stats)

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
        observations.append(_to_observation(m, team_id))
        if len(observations) >= n:
            break
    return observations


def get_h2h_matches(db: Session, team_a_id: int, team_b_id: int, limit: int = 6,
                     history: HistoryCache | None = None) -> list[Match]:
    if history is not None:
        return history.h2h_matches(team_a_id, team_b_id, limit)

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
