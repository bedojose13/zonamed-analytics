"""Simulación Monte Carlo multi-mercado — módulo 3 del brief.

Por qué simular en vez de solo calcular cerrado
--------------------------------------------------
Los mercados de córners y tarjetas son eventos discretos y varios mercados (hándicap de
córners, "ambos anotan", probabilidad de roja) involucran INTERACCIONES entre variables
(goles, córners y tarjetas no son independientes entre sí: partidos trabados con muchas faltas
tienden a tener marcadores bajos). Simular escenarios completos partido a partido — en vez de
calcular cada mercado por separado con fórmulas cerradas independientes — captura esa
estructura conjunta de forma directa y hace trivial responder preguntas compuestas
("P(over 9.5 córners Y over 3.5 tarjetas)") sin derivar la distribución conjunta a mano.

Método
------
Para cada una de las N=100,000 iteraciones se muestrea, de forma vectorizada con NumPy:
  1. El marcador (goles_local, goles_visita) como un DRAW CATEGÓRICO directo sobre la matriz de
     probabilidades del Poisson biparamétrico + ajuste Dixon-Coles (`poisson_1x2.score_probability_matrix`).
     Esto es exacto (no hay error de muestreo en la forma de la distribución, solo en el
     conteo de cada celda) y evita tener que simular X e Y por separado ignorando su
     correlación de marcador bajo.
  2. Córners local/visitante ~ Binomial Negativa(μ, α) independientes (aproximación razonable:
     la correlación córners-goles es débil comparada con la correlación goles-goles de
     Dixon-Coles, que ya se maneja en el paso 1).
  3. Tarjetas local/visitante ~ Binomial Negativa(μ, α) independientes, con α menor (menos
     sobredispersión que córners: las tarjetas están más acotadas por la rigurosidad fija del
     árbitro dentro de un mismo partido).
  4. Tarjetas rojas ~ Poisson(μ_rojas) — evento raro, la aproximación Poisson (Var=media) es
     adecuada cuando μ es pequeño (<0.5), que es el caso típico (rojas ≈ 1 cada 6-7 partidos).

Con 100,000 iteraciones el error estándar de una probabilidad estimada p es
√(p(1-p)/100000) ≤ 0.16% en el peor caso (p=0.5) — más que suficiente precisión para líneas
de mercado que se cotizan en pasos de 1 punto porcentual.
"""
from __future__ import annotations

import numpy as np

from app.core.config import get_settings
from app.predictive.corners_model import NegativeBinomialParams
from app.predictive.poisson_1x2 import score_probability_matrix

settings = get_settings()

CORNER_BUCKET_MAX = 14
CARD_BUCKET_MAX = 9


def _sample_negative_binomial(rng: np.random.Generator, params: NegativeBinomialParams, size: int) -> np.ndarray:
    n, p = params.to_n_p()
    return rng.negative_binomial(n, p, size=size)


def _distribution_dict(totals: np.ndarray, bucket_max: int) -> dict[str, float]:
    clipped = np.minimum(totals, bucket_max)
    counts = np.bincount(clipped, minlength=bucket_max + 1)
    probs = counts / totals.size
    labels = [str(i) for i in range(bucket_max)] + [f"{bucket_max}+"]
    return {label: round(float(p), 5) for label, p in zip(labels, probs)}


def _over_under_lines(totals: np.ndarray, lines: list[float]) -> list[dict]:
    out = []
    ev = float(totals.mean())
    for line in lines:
        prob_over = float(np.mean(totals > line))
        out.append({"line": line, "prob_over": round(prob_over, 4),
                    "prob_under": round(1 - prob_over, 4), "expected_value": round(ev, 3)})
    return out


def run_monte_carlo(
    *,
    lambda_home_goals: float,
    lambda_away_goals: float,
    corner_params_home: NegativeBinomialParams,
    corner_params_away: NegativeBinomialParams,
    cards_mu_home: float,
    cards_mu_away: float,
    expected_red_total: float,
    rho: float = -0.08,
    corner_lines: list[float] | None = None,
    card_lines: list[float] | None = None,
    n_simulations: int | None = None,
    seed: int | None = None,
) -> dict:
    n = n_simulations or settings.monte_carlo_iterations
    rng = np.random.default_rng(seed if seed is not None else settings.monte_carlo_random_seed)

    matrix = score_probability_matrix(lambda_home_goals, lambda_away_goals, rho)
    max_goals = matrix.shape[0] - 1
    flat_probs = matrix.flatten()
    flat_probs = flat_probs / flat_probs.sum()
    draws = rng.choice(flat_probs.size, size=n, p=flat_probs)
    home_goals = draws // matrix.shape[1]
    away_goals = draws % matrix.shape[1]

    cards_alpha = 0.12
    home_corners = _sample_negative_binomial(rng, corner_params_home, n)
    away_corners = _sample_negative_binomial(rng, corner_params_away, n)
    home_cards = _sample_negative_binomial(rng, NegativeBinomialParams(cards_mu_home, cards_alpha), n)
    away_cards = _sample_negative_binomial(rng, NegativeBinomialParams(cards_mu_away, cards_alpha), n)
    red_cards_total = rng.poisson(max(expected_red_total, 1e-4), size=n)

    total_corners = home_corners + away_corners
    total_cards = home_cards + away_cards

    prob_home_win = float(np.mean(home_goals > away_goals))
    prob_draw = float(np.mean(home_goals == away_goals))
    prob_away_win = float(np.mean(home_goals < away_goals))

    pairs, counts = np.unique(np.stack([home_goals, away_goals], axis=1), axis=0, return_counts=True)
    order = np.argsort(-counts)[:6]
    top_scorelines = [
        {"home_goals": int(pairs[i][0]), "away_goals": int(pairs[i][1]), "probability": round(float(counts[i] / n), 4)}
        for i in order
    ]

    corner_lines = corner_lines or [7.5, 8.5, 9.5, 10.5, 11.5]
    card_lines = card_lines or [2.5, 3.5, 4.5, 5.5]

    return {
        "n_simulations": n,
        "prob_home_win": round(prob_home_win, 4),
        "prob_draw": round(prob_draw, 4),
        "prob_away_win": round(prob_away_win, 4),
        "top_scorelines": top_scorelines,
        "total_corners_distribution": _distribution_dict(total_corners, CORNER_BUCKET_MAX),
        "total_cards_distribution": _distribution_dict(total_cards, CARD_BUCKET_MAX),
        "corner_lines": _over_under_lines(total_corners, corner_lines),
        "card_lines": _over_under_lines(total_cards, card_lines),
        "prob_both_teams_score": round(float(np.mean((home_goals > 0) & (away_goals > 0))), 4),
        "prob_red_card_shown": round(float(np.mean(red_cards_total >= 1)), 4),
    }
