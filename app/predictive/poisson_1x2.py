"""Modelo 1X2: Poisson Biparamétrico (Dixon & Coles, 1997) — módulo 3 del brief.

Lógica matemática
------------------
Se modelan los goles del local y del visitante como dos variables Poisson INDEPENDIENTES con
parámetros propios (de ahí "biparamétrico": λ_local y λ_visitante, en vez de un único λ
compartido):

    P(X_local = x) = e^{-λ_local} λ_local^x / x!
    P(X_visita = y) = e^{-λ_visita} λ_visita^y / y!

La independencia entre X e Y es una simplificación conocida: en la realidad los marcadores
bajos (0-0, 1-0, 0-1, 1-1) ocurren con más frecuencia de la que predice el producto de dos
Poisson independientes (los equipos "juegan con el resultado" cuando el marcador está apretado).
Dixon & Coles corrigen esto con un factor multiplicativo τ que solo toca esas 4 celdas:

    τ(0,0) = 1 − λ_local·λ_visita·ρ
    τ(1,0) = 1 + λ_visita·ρ
    τ(0,1) = 1 + λ_local·ρ
    τ(1,1) = 1 − ρ
    τ(x,y) = 1                              en cualquier otro caso

    P(X=x, Y=y) = τ(x,y) · Poisson(x; λ_local) · Poisson(y; λ_visita)

ρ (rho) es un único parámetro libre que se calibra por Máxima Verosimilitud sobre el histórico
de la liga (`fit_rho`); típicamente resulta ligeramente negativo (entre -0.15 y -0.02) en
ligas con pocos goles por partido como la Dimayor. Con ρ=0 el modelo colapsa al Poisson
biparamétrico "puro" sin ajuste de marcadores bajos.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from joblib import dump, load
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

from app.core.config import get_settings

settings = get_settings()

MAX_GOALS_GRID = 10  # suficiente para capturar >99.9% de la masa de probabilidad en fútbol
DEFAULT_RHO = -0.08


def dixon_coles_tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lambda_home * lambda_away * rho
    if x == 0 and y == 1:
        return 1 + lambda_home * rho
    if x == 1 and y == 0:
        return 1 + lambda_away * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def score_probability_matrix(
    lambda_home: float, lambda_away: float, rho: float = -0.08, max_goals: int = MAX_GOALS_GRID,
) -> np.ndarray:
    """Matriz [x=goles_local, y=goles_visita] de P(X=x, Y=y), tamaño (max_goals+1)^2."""
    home_pmf = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    away_pmf = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    matrix = np.outer(home_pmf, away_pmf)

    for x in range(2):
        for y in range(2):
            matrix[x, y] *= dixon_coles_tau(x, y, lambda_home, lambda_away, rho)

    matrix /= matrix.sum()  # renormaliza tras truncar la cola y aplicar τ
    return matrix


@dataclass
class OneXTwoProbabilities:
    home_win: float
    draw: float
    away_win: float


def one_x_two_from_matrix(matrix: np.ndarray) -> OneXTwoProbabilities:
    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    return OneXTwoProbabilities(home_win=home_win, draw=draw, away_win=away_win)


def fit_rho(historical_lambda_pairs: list[tuple[float, float, int, int]]) -> float:
    """Calibra ρ por Máxima Verosimilitud sobre partidos históricos.

    `historical_lambda_pairs`: lista de (λ_local, λ_visita, goles_local_reales, goles_visita_reales),
    donde λ_local/λ_visita son los goles esperados YA estimados por el pipeline de features para
    ese partido (no los goles reales) — así ρ se calibra específicamente para corregir el sesgo
    de marcadores bajos del modelo, dado lo que el modelo ya sabía antes del partido.
    """
    if len(historical_lambda_pairs) < 20:
        return -0.08  # prior razonable de la literatura si no hay suficiente histórico

    def neg_log_likelihood(rho: float) -> float:
        total = 0.0
        for lam_h, lam_a, gh, ga in historical_lambda_pairs:
            p = poisson.pmf(gh, lam_h) * poisson.pmf(ga, lam_a)
            if gh <= 1 and ga <= 1:
                p *= dixon_coles_tau(gh, ga, lam_h, lam_a, rho)
            total -= np.log(max(p, 1e-10))
        return total

    result = minimize_scalar(neg_log_likelihood, bounds=(-0.35, 0.35), method="bounded")
    return float(result.x)


def most_likely_scoreline(matrix: np.ndarray) -> tuple[int, int]:
    idx = int(np.argmax(matrix))
    home_goals, away_goals = divmod(idx, matrix.shape[1])
    return home_goals, away_goals


def save_rho(rho: float) -> None:
    dump(rho, settings.models_dir / "dixon_coles_rho.joblib")


def load_rho() -> float:
    path = settings.models_dir / "dixon_coles_rho.joblib"
    return float(load(path)) if path.exists() else DEFAULT_RHO
