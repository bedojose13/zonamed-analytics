"""Corrección por XGBoost sobre el prior Poisson — mitad del ensemble del módulo 3 del brief.

Por qué ensemble y no solo Poisson
------------------------------------
El Poisson biparamétrico asume que λ_local y λ_visita se combinan de forma puramente
multiplicativa (ataque × defensa) y no puede capturar interacciones no lineales entre features
— p. ej. que la fatiga por altitud pega más fuerte cuando ADEMÁS hay poco descanso, o que la
rigurosidad del árbitro importa menos en marcadores ya definidos. Un XGBoostRegressor entrenado
sobre el mismo vector de features (`MatchFeatureSet.as_ml_row`) aprende esas interacciones
directamente de los datos. El ensemble final pondera ambos:

    λ_final = w_poisson · λ_poisson + w_xgb · ŷ_xgboost

con `w_poisson + w_xgb = 1`. Por defecto se favorece el prior Poisson (interpretable, estable
con pocos datos) y XGBoost aporta una corrección moderada — evita que el ensemble "delire" en
partidos con historial corto, un riesgo real en una liga de 20 equipos con pocas jornadas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from joblib import dump, load
from xgboost import XGBRegressor

from app.core.config import get_settings

settings = get_settings()

FEATURE_COLUMNS = [
    "expected_home_goals_poisson", "expected_away_goals_poisson", "goal_supremacy_poisson",
    "expected_home_corners", "expected_away_corners", "expected_home_fouls", "expected_away_fouls",
    "expected_home_cards", "expected_away_cards", "fatigue_penalty_away", "referee_strictness_index",
    "h2h_intensity", "is_derby", "altitude_gap_m", "temperature_c", "humidity_pct",
    "home_rest_days", "away_rest_days",
]

ENSEMBLE_WEIGHT_POISSON = 0.55
ENSEMBLE_WEIGHT_XGB = 0.45

_XGB_PARAMS = dict(
    n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.8,
    colsample_bytree=0.8, reg_lambda=1.5, objective="count:poisson", random_state=42,
)


def rows_to_matrix(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


def train_goal_models(feature_rows: list[dict], home_goals: list[int], away_goals: list[int]) -> None:
    X = rows_to_matrix(feature_rows)
    model_home = XGBRegressor(**_XGB_PARAMS).fit(X, np.asarray(home_goals))
    model_away = XGBRegressor(**_XGB_PARAMS).fit(X, np.asarray(away_goals))
    dump(model_home, settings.models_dir / "xgb_home_goals.joblib")
    dump(model_away, settings.models_dir / "xgb_away_goals.joblib")


def load_goal_models() -> tuple[XGBRegressor, XGBRegressor] | None:
    home_path = settings.models_dir / "xgb_home_goals.joblib"
    away_path = settings.models_dir / "xgb_away_goals.joblib"
    if not home_path.exists() or not away_path.exists():
        return None
    return load(home_path), load(away_path)


def blend_with_poisson(
    poisson_home: float, poisson_away: float,
    xgb_home: float | None, xgb_away: float | None,
) -> tuple[float, float]:
    if xgb_home is None or xgb_away is None:
        return poisson_home, poisson_away
    final_home = ENSEMBLE_WEIGHT_POISSON * poisson_home + ENSEMBLE_WEIGHT_XGB * max(xgb_home, 0.05)
    final_away = ENSEMBLE_WEIGHT_POISSON * poisson_away + ENSEMBLE_WEIGHT_XGB * max(xgb_away, 0.05)
    return float(final_home), float(final_away)


def predict_goal_correction(feature_row: dict) -> tuple[float, float] | tuple[None, None]:
    models = load_goal_models()
    if models is None:
        return None, None
    model_home, model_away = models
    X = rows_to_matrix([feature_row])
    return float(model_home.predict(X)[0]), float(model_away.predict(X)[0])
