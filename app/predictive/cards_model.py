"""Modelo de Tarjetas y Faltas: GLM — módulo 3 del brief.

Dos niveles de modelado
------------------------
1) Nivel EQUIPO (cuántas tarjetas totales en el partido): GLM Poisson con función de enlace
   logarítmica, log(μ) = β₀ + β₁·xFaltas + β₂·rigurosidad_árbitro + β₃·intensidad_H2H +
   β₄·índice_agresividad. El enlace log garantiza μ > 0 sin restricciones adicionales y hace
   que cada β se interprete como un efecto multiplicativo (exp(β)) sobre la tasa esperada de
   tarjetas — igual que en xCards, pero aquí los coeficientes se ESTIMAN de los datos en vez de
   fijarse a mano, permitiendo que el modelo descubra, por ejemplo, que la rigurosidad del
   árbitro pesa más que la agresividad del plantel si eso es lo que muestran los datos.

2) Nivel JUGADOR (quién es más propenso a ver tarjeta): GLM Binomial con enlace logit —
   regresión logística clásica — sobre el evento binario "vio tarjeta amarilla":

       logit(P(tarjeta)) = β₀ + β₁·card_proneness_jugador + β₂·rigurosidad_árbitro

   `card_proneness_jugador` ya resume el historial disciplinario individual (ver seed/feature
   engineering de jugador). El GLM aprende cómo ese perfil interactúa con el árbitro asignado
   para dar una probabilidad de reserva específica del partido, no solo un promedio histórico
   plano.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from joblib import dump, load

from app.core.config import get_settings

settings = get_settings()

TEAM_CARD_FEATURES = ["expected_fouls", "referee_strictness_index", "h2h_intensity", "aggression_index"]
PLAYER_CARD_FEATURES = ["card_proneness_index", "referee_strictness_index"]


def train_team_card_model(df: pd.DataFrame, target_col: str = "cards_actual"):
    X = sm.add_constant(df[TEAM_CARD_FEATURES])
    y = df[target_col]
    model = sm.GLM(y, X, family=sm.families.Poisson()).fit()
    dump(model, settings.models_dir / "glm_team_cards.joblib")
    return model


def train_player_card_model(df: pd.DataFrame, target_col: str = "booked"):
    X = sm.add_constant(df[PLAYER_CARD_FEATURES])
    y = df[target_col]
    model = sm.GLM(y, X, family=sm.families.Binomial()).fit()
    dump(model, settings.models_dir / "glm_player_cards.joblib")
    return model


def _load(name: str):
    path = settings.models_dir / name
    return load(path) if path.exists() else None


def predict_team_cards(feature_row: dict, fallback_mu: float) -> float:
    model = _load("glm_team_cards.joblib")
    if model is None:
        return fallback_mu
    row = {**{c: 0.0 for c in TEAM_CARD_FEATURES}, **feature_row}
    X = sm.add_constant(pd.DataFrame([row])[TEAM_CARD_FEATURES], has_constant="add")
    X = X.reindex(columns=["const", *TEAM_CARD_FEATURES], fill_value=1.0)
    return float(model.predict(X)[0])


def predict_player_booking_probability(feature_row: dict, fallback_p: float) -> float:
    model = _load("glm_player_cards.joblib")
    if model is None:
        return fallback_p
    row = {**{c: 0.0 for c in PLAYER_CARD_FEATURES}, **feature_row}
    X = sm.add_constant(pd.DataFrame([row])[PLAYER_CARD_FEATURES], has_constant="add")
    X = X.reindex(columns=["const", *PLAYER_CARD_FEATURES], fill_value=1.0)
    return float(np.clip(model.predict(X)[0], 0.01, 0.95))
