"""Punto de entrada único del motor predictivo: combina Poisson+XGBoost (goles), Binomial
Negativa (córners), GLM (tarjetas) y la simulación Monte Carlo en un solo resultado coherente
por partido. Es la función que consumen tanto los endpoints de la API como el script de
entrenamiento/backfill (para poblar `Prediction` de partidos ya jugados y así alimentar la
vista de auditoría real-vs-proyectado)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Match
from app.predictive import monte_carlo
from app.predictive.corners_model import NegativeBinomialParams, predict_corner_params
from app.predictive.poisson_1x2 import (
    load_rho,
    most_likely_scoreline,
    one_x_two_from_matrix,
    score_probability_matrix,
)
from app.predictive.xgboost_model import blend_with_poisson, predict_goal_correction
from app.predictive.cards_model import predict_team_cards
from app.services.feature_engineering import MatchFeatureSet, build_feature_set
from app.services.team_history import HistoryCache

settings = get_settings()

LEAGUE_BASE_RED_RATE = 0.32  # rojas totales promedio por partido en la liga


def _expected_red_total(features: MatchFeatureSet) -> float:
    return LEAGUE_BASE_RED_RATE * features.referee_strictness_index * (0.7 + 0.3 * features.h2h_intensity)


def generate_prediction(
    db: Session, match: Match, *, exclude_this_match: bool = True,
    corner_line: float | None = None, card_line: float | None = None,
    history: HistoryCache | None = None,
) -> dict:
    """`history`: pásalo (un `HistoryCache` ya construido) cuando el caller vaya a generar
    predicciones para VARIOS partidos en el mismo request (ver app/api/routers/proximos.py y
    jugados.py) — evita repetir decenas de consultas por partido contra la base remota. Si no
    se pasa, se construye uno aquí mismo: incluso para un solo partido, 2 consultas en bloque
    salen más baratas que las ~10 consultas puntuales por equipo que hacía el camino viejo."""
    if history is None:
        history = HistoryCache(db)

    features = build_feature_set(db, match, exclude_this_match=exclude_this_match, history=history)
    feature_row = features.as_ml_row()

    xgb_home, xgb_away = predict_goal_correction(feature_row)
    final_home_goals, final_away_goals = blend_with_poisson(
        features.expected_home_goals_poisson, features.expected_away_goals_poisson, xgb_home, xgb_away,
    )

    rho = load_rho()
    matrix = score_probability_matrix(final_home_goals, final_away_goals, rho)
    one_x_two = one_x_two_from_matrix(matrix)
    best_home, best_away = most_likely_scoreline(matrix)

    corner_params_home = predict_corner_params(
        {"expected_corners_rate_model": features.expected_home_corners, "wing_play_index": 0.5,
         "possession_pct": 52.0, "is_home": 1.0},
        fallback_mu=features.expected_home_corners,
    )
    corner_params_away = predict_corner_params(
        {"expected_corners_rate_model": features.expected_away_corners, "wing_play_index": 0.5,
         "possession_pct": 48.0, "is_home": 0.0},
        fallback_mu=features.expected_away_corners,
    )

    cards_mu_home = predict_team_cards(
        {"expected_fouls": features.expected_home_fouls, "referee_strictness_index": features.referee_strictness_index,
         "h2h_intensity": features.h2h_intensity, "aggression_index": 1.0},
        fallback_mu=features.expected_home_cards,
    )
    cards_mu_away = predict_team_cards(
        {"expected_fouls": features.expected_away_fouls, "referee_strictness_index": features.referee_strictness_index,
         "h2h_intensity": features.h2h_intensity, "aggression_index": 1.0},
        fallback_mu=features.expected_away_cards,
    )

    expected_red_total = _expected_red_total(features)
    corner_line_used = corner_line or settings.default_corner_line
    card_line_used = card_line or settings.default_card_line

    mc = monte_carlo.run_monte_carlo(
        lambda_home_goals=final_home_goals, lambda_away_goals=final_away_goals,
        corner_params_home=corner_params_home, corner_params_away=corner_params_away,
        cards_mu_home=cards_mu_home, cards_mu_away=cards_mu_away,
        expected_red_total=expected_red_total, rho=rho,
        corner_lines=sorted({corner_line_used - 1, corner_line_used, corner_line_used + 1}),
        card_lines=sorted({card_line_used - 1, card_line_used, card_line_used + 1}),
    )

    corner_line_entry = next((l for l in mc["corner_lines"] if l["line"] == corner_line_used), mc["corner_lines"][0])
    card_line_entry = next((l for l in mc["card_lines"] if l["line"] == card_line_used), mc["card_lines"][0])

    summary = {
        "model_version": "v1",
        "prob_home_win": mc["prob_home_win"], "prob_draw": mc["prob_draw"], "prob_away_win": mc["prob_away_win"],
        "expected_home_goals": round(final_home_goals, 3), "expected_away_goals": round(final_away_goals, 3),
        "most_likely_score": f"{best_home}-{best_away}",
        "expected_home_corners": round(corner_params_home.mu, 2), "expected_away_corners": round(corner_params_away.mu, 2),
        "corner_line_used": corner_line_used, "prob_over_corner_line": corner_line_entry["prob_over"],
        "expected_home_cards": round(cards_mu_home, 2), "expected_away_cards": round(cards_mu_away, 2),
        "expected_total_fouls": round(features.expected_home_fouls + features.expected_away_fouls, 1),
        "card_line_used": card_line_used, "prob_over_card_line": card_line_entry["prob_over"],
        "prob_red_card_shown": mc["prob_red_card_shown"],
    }

    return {
        "summary": summary, "monte_carlo": mc, "feature_snapshot": feature_row,
        "one_x_two_from_matrix": {  # expuesto por si se quiere auditar contra mc (deben coincidir ~)
            "home_win": one_x_two.home_win, "draw": one_x_two.draw, "away_win": one_x_two.away_win,
        },
    }
