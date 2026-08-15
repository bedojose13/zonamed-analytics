"""Entrena/calibra todos los componentes del ensemble sobre el histórico de partidos FINISHED
y guarda los artefactos en `settings.models_dir`. Debe correrse después de `sync_real_data` (o
del seed sintético de demo) y se re-corre en cada arranque del proceso — es barato (sin
llamadas a APIs externas) y así los modelos de córners/tarjetas van mejorando solos a medida
que el backfill diario de estadísticas reales avanza (ver app/scripts/sync_real_data.py).

Nota de rendimiento: TODO acceso a datos históricos aquí pasa por `HistoryCache` / consultas
`.in_(...)` en bloque, nunca una consulta por partido — con datos reales (cientos de partidos)
contra una base remota, una consulta por partido son miles de idas y vueltas de red (minutos);
precargar todo una sola vez lo deja en segundos. Ver app/services/team_history.py.

Uso:
    python -m app.scripts.train_models
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import session_scope
from app.models import Match, MatchCornerStats, MatchDisciplineStats, MatchStatus, PlayerMatchStat, Referee, Rivalry, Team
from app.predictive.cards_model import train_player_card_model, train_team_card_model
from app.predictive.corners_model import train_corner_model
from app.predictive.poisson_1x2 import fit_rho, save_rho
from app.predictive.xgboost_model import train_goal_models
from app.services.feature_engineering import build_feature_set
from app.services.league_baseline import compute_league_averages, save_league_averages
from app.services.team_history import HistoryCache
from app.services.xcards import h2h_intensity_multiplier, referee_strictness

MIN_ROWS_FOR_STATS_MODELS = 40  # ~20 partidos con estadísticas ya backfilled (2 filas c/u)


def _finished_matches(db: Session) -> list[Match]:
    stmt = select(Match).where(Match.status == MatchStatus.FINISHED).order_by(Match.kickoff.asc())
    return list(db.execute(stmt).scalars().all())


def _rivalry_lookup(db: Session) -> dict[frozenset, Rivalry]:
    rivalries = db.execute(select(Rivalry)).scalars().all()
    return {frozenset((r.team_a_id, r.team_b_id)): r for r in rivalries}


def train_goals_and_rho(db: Session, matches: list[Match], history: HistoryCache) -> None:
    feature_rows, home_goals, away_goals, rho_pairs = [], [], [], []
    for match in matches:
        fs = build_feature_set(db, match, exclude_this_match=True, history=history)
        feature_rows.append(fs.as_ml_row())
        home_goals.append(match.home_goals)
        away_goals.append(match.away_goals)
        rho_pairs.append((fs.expected_home_goals_poisson, fs.expected_away_goals_poisson,
                           match.home_goals, match.away_goals))

    train_goal_models(feature_rows, home_goals, away_goals)
    rho = fit_rho(rho_pairs)
    save_rho(rho)
    print(f"  -> XGBoost goles entrenado sobre {len(matches)} partidos. ρ (Dixon-Coles) calibrado = {rho:.4f}")


def train_corners(db: Session, matches: list[Match], history: HistoryCache) -> None:
    stats_ready = [m for m in matches if m.stats_synced]
    if not stats_ready:
        print("  -> Córners: 0 observaciones con estadísticas reales todavía — se usa el estimado "
              "analítico de liga mientras tanto.")
        return

    corner_rows_by_match: dict[int, list[MatchCornerStats]] = defaultdict(list)
    match_ids = [m.id for m in stats_ready]
    for cs in db.execute(select(MatchCornerStats).where(MatchCornerStats.match_id.in_(match_ids))).scalars().all():
        corner_rows_by_match[cs.match_id].append(cs)

    rows = []
    for match in stats_ready:
        fs = build_feature_set(db, match, exclude_this_match=True, history=history)
        for cs in corner_rows_by_match.get(match.id, []):
            expected = fs.expected_home_corners if cs.is_home else fs.expected_away_corners
            rows.append({
                "expected_corners_rate_model": expected,
                "wing_play_index": cs.wing_play_index,
                "possession_pct": cs.possession_pct,
                "is_home": float(cs.is_home),
                "corners_actual": cs.corners_won,
            })
    if len(rows) < MIN_ROWS_FOR_STATS_MODELS:
        print(f"  -> Córners: solo {len(rows)} observaciones con estadísticas reales todavía "
              f"(backfill en curso) — se usa el estimado analítico de liga mientras tanto.")
        return
    df = pd.DataFrame(rows)
    train_corner_model(df)
    print(f"  -> Binomial Negativa de córners entrenada sobre {len(df)} observaciones equipo-partido reales.")


def train_cards(db: Session, matches: list[Match], history: HistoryCache) -> None:
    stats_ready = [m for m in matches if m.stats_synced]
    if not stats_ready:
        print("  -> Tarjetas: 0 observaciones con estadísticas reales todavía — se usa el estimado "
              "analítico de liga mientras tanto.")
        return

    match_ids = [m.id for m in stats_ready]
    rivalries = _rivalry_lookup(db)

    discipline_by_match: dict[int, list[MatchDisciplineStats]] = defaultdict(list)
    for ds in db.execute(
        select(MatchDisciplineStats).where(MatchDisciplineStats.match_id.in_(match_ids))
    ).scalars().all():
        discipline_by_match[ds.match_id].append(ds)

    # Nota: no se ingesta detalle por jugador desde la API real (el plan gratuito lo cobraría
    # aparte en llamadas de alineaciones) — PlayerMatchStat queda vacío y el modelo de riesgo
    # individual por jugador se omite. Este bloque se deja por si en el futuro se agrega esa
    # fuente de datos.
    player_by_match: dict[int, list[PlayerMatchStat]] = defaultdict(list)
    for ps in db.execute(
        select(PlayerMatchStat).where(PlayerMatchStat.match_id.in_(match_ids))
    ).scalars().all():
        player_by_match[ps.match_id].append(ps)

    team_rows, player_rows = [], []
    for match in stats_ready:
        fs = build_feature_set(db, match, exclude_this_match=True, history=history)
        rivalry = rivalries.get(frozenset((match.home_team_id, match.away_team_id)))
        h2h_mult = h2h_intensity_multiplier(db, match.home_team_id, match.away_team_id, rivalry, history=history)
        strictness = referee_strictness(match.referee)

        for ds in discipline_by_match.get(match.id, []):
            expected_fouls = fs.expected_home_fouls if ds.is_home else fs.expected_away_fouls
            team_rows.append({
                "expected_fouls": expected_fouls, "referee_strictness_index": strictness,
                "h2h_intensity": h2h_mult, "aggression_index": ds.aggression_index,
                "cards_actual": ds.yellow_cards + ds.red_cards,
            })

        for ps in player_by_match.get(match.id, []):
            player_rows.append({
                "card_proneness_index": ps.player.card_proneness_index or 1.0,
                "referee_strictness_index": strictness,
                "booked": int(ps.yellow_card),
            })

    if len(team_rows) < MIN_ROWS_FOR_STATS_MODELS:
        print(f"  -> Tarjetas de equipo: solo {len(team_rows)} observaciones reales todavía "
              f"(backfill en curso) — se usa el estimado analítico de liga mientras tanto.")
    else:
        train_team_card_model(pd.DataFrame(team_rows))
        print(f"  -> GLM tarjetas equipo entrenado sobre {len(team_rows)} filas reales.")

    if len(player_rows) < MIN_ROWS_FOR_STATS_MODELS:
        print("  -> Tarjetas por jugador: sin datos reales de jugadores (no se ingestan alineaciones "
              "en el plan gratuito) — panel de riesgo individual queda desactivado.")
    else:
        train_player_card_model(pd.DataFrame(player_rows))
        print(f"  -> GLM tarjetas jugador entrenado sobre {len(player_rows)} filas.")


def run() -> None:
    with session_scope() as db:
        # Precarga equipos/árbitros en el identity map de la sesión: como son pocas filas
        # (~20 equipos, ~15 árbitros), esto hace que TODO acceso posterior a `match.home_team`,
        # `match.away_team` o `match.referee` en este módulo se resuelva en memoria en vez de
        # disparar una consulta perezosa por cada partido.
        db.execute(select(Team)).scalars().all()
        db.execute(select(Referee)).scalars().all()

        matches = _finished_matches(db)
        if len(matches) < 20:
            print(f"Solo hay {len(matches)} partidos FINISHED todavía — se omite el entrenamiento "
                  "hasta que avance la sincronización (app/scripts/sync_real_data.py).")
            return

        print(f"Entrenando ensemble sobre {len(matches)} partidos históricos...")

        league_avg = compute_league_averages(db)
        save_league_averages(league_avg)
        print(f"  -> Promedios de liga recalibrados: goles={league_avg.goals_for:.2f}, "
              f"córners={league_avg.corners_for:.2f}, faltas={league_avg.fouls_for:.2f}, "
              f"amarillas/árbitro/partido={league_avg.yellow_per_match:.2f}")

        history = HistoryCache(db)
        train_goals_and_rho(db, matches, history)
        train_corners(db, matches, history)
        train_cards(db, matches, history)

    print("Entrenamiento completo. Artefactos guardados en artifacts/models/.")


if __name__ == "__main__":
    run()
