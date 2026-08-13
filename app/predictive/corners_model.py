"""Modelo de Córners: Regresión Binomial Negativa — módulo 3 del brief.

Por qué Binomial Negativa y no Poisson
-----------------------------------------
Un supuesto central de la distribución Poisson es que **media = varianza**. Los córners no
cumplen esto: partidos con estilos de juego muy directos por bandas generan explosiones de
córners muy por encima de la media, mientras que partidos de posesión estéril por el centro
generan muchos menos — la varianza observada de córners por partido en fútbol es
consistentemente mayor que la media (sobredispersión). Ignorar esto subestima la probabilidad
de las colas (partidos de 12+ o 2- córners), que es exactamente donde viven las líneas de
Over/Under.

La Binomial Negativa (parametrización NB2) modela esto añadiendo un parámetro de dispersión α:

    Var(Y) = μ + α·μ²

Con α=0 colapsa exactamente a Poisson (Var=μ); α>0 (el caso típico en fútbol) infla la varianza
por encima de la media. Se usa `statsmodels.discrete_model.NegativeBinomial`, que estima por
Máxima Verosimilitud tanto los coeficientes de regresión de μ (en función del xC ya calculado
por el rate-model, el índice de juego por bandas y la posesión) como α, simultáneamente.

Para el muestreo en Monte Carlo, la parametrización (n, p) de `numpy.random.negative_binomial`
se obtiene de (μ, α) vía:

    n = 1 / α          p = n / (n + μ)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from joblib import dump, load

from app.core.config import get_settings

settings = get_settings()

CORNER_FEATURE_COLUMNS = ["expected_corners_rate_model", "wing_play_index", "possession_pct", "is_home"]
FALLBACK_ALPHA = 0.18  # sobredispersión moderada, calibrada a partir de ligas comparables


@dataclass
class NegativeBinomialParams:
    mu: float
    alpha: float

    def to_n_p(self) -> tuple[float, float]:
        alpha = max(self.alpha, 1e-4)
        n = 1.0 / alpha
        p = n / (n + self.mu)
        return n, p


def train_corner_model(df: pd.DataFrame, target_col: str = "corners_actual"):
    """`df` debe traer las columnas de CORNER_FEATURE_COLUMNS + target_col, una fila por
    (equipo, partido) histórico."""
    X = sm.add_constant(df[CORNER_FEATURE_COLUMNS])
    y = df[target_col]
    model = sm.NegativeBinomial(y, X).fit(disp=0, maxiter=200)
    dump(model, settings.models_dir / "nb_corners.joblib")
    return model


def load_corner_model():
    path = settings.models_dir / "nb_corners.joblib"
    return load(path) if path.exists() else None


def predict_corner_params(feature_row: dict, fallback_mu: float) -> NegativeBinomialParams:
    model = load_corner_model()
    if model is None:
        return NegativeBinomialParams(mu=fallback_mu, alpha=FALLBACK_ALPHA)

    row = {**{c: 0.0 for c in CORNER_FEATURE_COLUMNS}, **feature_row}
    X = sm.add_constant(pd.DataFrame([row])[CORNER_FEATURE_COLUMNS], has_constant="add")
    # add_constant no garantiza el orden/columna 'const' si falta variación; reordenamos a mano.
    X = X.reindex(columns=["const", *CORNER_FEATURE_COLUMNS], fill_value=1.0)
    mu = float(model.predict(X)[0])
    alpha = float(model.params.get("alpha", FALLBACK_ALPHA)) if hasattr(model, "params") else FALLBACK_ALPHA
    return NegativeBinomialParams(mu=max(mu, 0.3), alpha=max(alpha, 0.02))
