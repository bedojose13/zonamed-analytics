"""Entrena/calibra todos los componentes del ensemble sobre el histórico de partidos FINISHED
y guarda los artefactos en `settings.models_dir`. Debe correrse después de `seed_db` (o de
cualquier ingestión real) y periódicamente conforme se acumulan más partidos jugados.

Uso:
    python -m app.scripts.train_models
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import session_scope
from app.models import Match, MatchCornerStats, MatchDisciplineStats, MatchStatus, PlayerMatchStat, Rivalry
from app.predictive.cards_model import train_player_card_model, train_team_card_model
from app.predictive.corners_model import train_corner_model
from app.predictive.poisson_1x2 import fit_rho, save_rho
from app.predictive.xgboost_model import train_goal_models
from app.services.feature_engineering import build_feature_set
from app.services.league_baseline import compute_league_averages, save_league_averages
from app.services.xcards import h2h_intensity_multiplier, referee_strictness


def _finished_matches(db: Session) -> list[Match]:
    stmt = select(Match).where(Match.status == MatchStatus.FINISHED).order_by(Match.kickoff.asc())
    return list(db.execute(stmt).scalars().all())


def train_goals_and_rho(db: Session, matches: list[Match]) -> None:
    feature_rows, home_goals, away_goals, rho_pairs = [], [], [], []
    for match in matches:
        fs = build_feature_set(db, match, exclude_this_match=True)
        feature_rows.append(fs.as_ml_row())
        home_goals.append(match.home_goals)
        away_goals.append(match.away_goals)
        rho_pairs.append((fs.expected_home_goals_poisson, fs.expected_away_goals_poisson,
                           match.home_goals, match.away_goals))

    train_goal_models(feature_rows, home_goals, away_goals)
    rho = fit_rho(rho_pairs)
    save_rho(rho)
    print(f"  -> XGBoost goles entrenado sobre {len(matches)} partidos. ρ (Dixon-Coles) calibrado = {rho:.4f}")


def train_corners(db: Session, matches: list[Match]) -> None:
    rows = []
    for match in matches:
        fs = build_feature_set(db, match, exclude_this_match=True)
        corner_rows = db.execute(
            select(MatchCornerStats).where(MatchCornerStats.match_id == match.id)
        ).scalars().all()
        for cs in corner_rows:
            expected = fs.expected_home_corners if cs.is_home else fs.expected_away_corners
            rows.append({
                "expected_corners_rate_model": expected,
                "wing_play_index": cs.wing_play_index,
                "possession_pct": cs.possession_pct,
                "is_home": float(cs.is_home),
                "corners_actual": cs.corners_won,
            })
    df = pd.DataFrame(rows)
    train_corner_model(df)
    print(f"  -> Binomial Negativa de córners entrenada sobre {len(df)} observaciones equipo-partido.")


def train_cards(db: Session, matches: list[Match]) -> None:
    team_rows, player_rows = [], []
    for match in matches:
        fs = build_feature_set(db, match, exclude_this_match=True)
        rivalry = db.execute(select(Rivalry).where(
            ((Rivalry.team_a_id == match.home_team_id) & (Rivalry.team_b_id == match.away_team_id))
            | ((Rivalry.team_a_id == match.away_team_id) & (Rivalry.team_b_id == match.home_team_id))
        )).scalars().first()
        h2h_mult = h2h_intensity_multiplier(db, match.home_team_id, match.away_team_id, rivalry)
        strictness = referee_strictness(match.referee)

        discipline_rows = db.execute(
            select(MatchDisciplineStats).where(MatchDisciplineStats.match_id == match.id)
        ).scalars().all()
        for ds in discipline_rows:
            expected_fouls = fs.expected_home_fouls if ds.is_home else fs.expected_away_fouls
            team_rows.append({
                "expected_fouls": expected_fouls, "referee_strictness_index": strictness,
                "h2h_intensity": h2h_mult, "aggression_index": ds.aggression_index,
                "cards_actual": ds.yellow_cards + ds.red_cards,
            })

        player_stats = db.execute(
            select(PlayerMatchStat).where(PlayerMatchStat.match_id == match.id)
        ).scalars().all()
        for ps in player_stats:
            player_rows.append({
                "card_proneness_index": ps.player.card_proneness_index or 1.0,
                "referee_strictness_index": strictness,
                "booked": int(ps.yellow_card),
            })

    train_team_card_model(pd.DataFrame(team_rows))
    train_player_card_model(pd.DataFrame(player_rows))
    print(f"  -> GLM tarjetas equipo entrenado sobre {len(team_rows)} filas; "
          f"GLM tarjetas jugador sobre {len(player_rows)} filas.")


def run() -> None:
    with session_scope() as db:
        matches = _finished_matches(db)
        if len(matches) < 20:
            raise SystemExit("Muy pocos partidos FINISHED para entrenar. Corre primero app/scripts/seed_db.py")

        print(f"Entrenando ensemble sobre {len(matches)} partidos históricos...")

        league_avg = compute_league_averages(db)
        save_league_averages(league_avg)
        print(f"  -> Promedios de liga recalibrados: goles={league_avg.goals_for:.2f}, "
              f"córners={league_avg.corners_for:.2f}, faltas={league_avg.fouls_for:.2f}, "
              f"amarillas/árbitro/partido={league_avg.yellow_per_match:.2f}")

        train_goals_and_rho(db, matches)
        train_corners(db, matches)
        train_cards(db, matches)

    print("Entrenamiento completo. Artefactos guardados en artifacts/models/.")


if __name__ == "__main__":
    run()
