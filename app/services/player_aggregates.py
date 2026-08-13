"""Recalcula los promedios disciplinarios agregados por jugador (tabla `players`) a partir del
detalle partido-a-partido en `player_match_stats`. Se ejecuta tras cargar/actualizar el
histórico (seed inicial o job periódico de refresco) para que la API pueda leer promedios ya
consolidados sin recalcularlos en cada request."""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus, Player, PlayerMatchStat

MIN_LEAGUE_AVG_YELLOW_RATE = 0.05  # guarda contra división por ~0 en ligas/temporadas muy nuevas


def refresh_player_aggregates(db: Session) -> None:
    # Nota: Postgres NO permite CAST(boolean AS float/integer) como sí lo tolera SQLite —
    # de ahí el CASE WHEN explícito en vez de func.cast(..., Float) sobre una columna booleana.
    league_avg_yellow = db.execute(
        select(func.avg(case((PlayerMatchStat.yellow_card, 1.0), else_=0.0)))
        .join(Match, Match.id == PlayerMatchStat.match_id)
        .where(Match.status == MatchStatus.FINISHED)
    ).scalar() or MIN_LEAGUE_AVG_YELLOW_RATE
    league_avg_yellow = max(float(league_avg_yellow), MIN_LEAGUE_AVG_YELLOW_RATE)

    players = db.execute(select(Player)).scalars().all()
    for player in players:
        stmt = (
            select(PlayerMatchStat)
            .join(Match, Match.id == PlayerMatchStat.match_id)
            .where(PlayerMatchStat.player_id == player.id, Match.status == MatchStatus.FINISHED)
        )
        stats = db.execute(stmt).scalars().all()
        if not stats:
            continue
        n = len(stats)
        player.avg_fouls_committed = sum(s.fouls_committed for s in stats) / n
        player.avg_fouls_received = sum(s.fouls_received for s in stats) / n
        player.avg_yellow_cards = sum(int(s.yellow_card) for s in stats) / n
        player.avg_red_cards = sum(int(s.red_card) for s in stats) / n
        player.card_proneness_index = round(player.avg_yellow_cards / league_avg_yellow, 3)
