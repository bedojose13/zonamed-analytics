"""Ponderación exponencial de forma reciente.

Lógica matemática
------------------
Un promedio simple sobre los últimos N partidos trata igual el partido de ayer que el de
hace 5 meses, lo cual ignora que la forma de un equipo (lesiones, moral, cambios tácticos)
cambia con el tiempo. Usamos un decaimiento exponencial por "vida media" (half-life):

    w_i = 0.5 ** (i / H)     con  i = 0 para el partido más reciente, 1 el anterior, ...

`H` (half_life) es el número de partidos que deben pasar para que el peso caiga a la mitad.
Con H=5 (valor por defecto, `settings.exponential_half_life_matches`), un partido de hace 5
jornadas pesa la mitad que el más reciente, y uno de hace 20 jornadas pesa 0.5**4 ≈ 6.25%.

El promedio ponderado de una métrica x sobre los últimos N partidos es:

    x̄_ponderado = Σ(w_i * x_i) / Σ(w_i)

que es exactamente lo que implementa `exponential_weighted_average` — equivalente a un EWMA
(Exponentially Weighted Moving Average) pero anclado a un half-life explícito e interpretable
en "número de partidos" en vez de un factor de suavizado abstracto.
"""
from __future__ import annotations

import numpy as np

from app.core.config import get_settings

settings = get_settings()


def decay_weights(n: int, half_life: float | None = None) -> np.ndarray:
    """Pesos exponenciales para `n` observaciones ordenadas de más reciente (índice 0) a
    más antigua (índice n-1)."""
    h = half_life or settings.exponential_half_life_matches
    idx = np.arange(n)
    return np.power(0.5, idx / h)


def exponential_weighted_average(
    values_most_recent_first: list[float], half_life: float | None = None
) -> float:
    """Promedio ponderado exponencialmente. `values_most_recent_first[0]` debe ser el dato
    del partido más reciente."""
    if not values_most_recent_first:
        return 0.0
    values = np.asarray(values_most_recent_first, dtype=float)
    weights = decay_weights(len(values), half_life)
    return float(np.sum(values * weights) / np.sum(weights))
