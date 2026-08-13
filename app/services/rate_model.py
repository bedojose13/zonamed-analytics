"""Combinación de tasas ataque/defensa — el mismo mecanismo matemático que Dixon & Coles (1997)
usan para goles, aquí generalizado a cualquier evento discreto (goles, córners, faltas).

Lógica matemática
------------------
Si λ_liga es la tasa media del evento en la liga (p. ej. córners por equipo por partido), y
cada equipo tiene:
  - un "factor de ataque" α_i = (tasa propia del evento a favor) / λ_liga
  - un "factor de defensa" δ_j = (tasa propia del evento en contra) / λ_liga

la tasa esperada del evento cuando el equipo i enfrenta al equipo j se estima como:

    λ_{i vs j} = λ_liga * α_i * δ_j

Interpretación: un equipo con α_i > 1 genera más del evento que el promedio de la liga; un
equipo con δ_j > 1 concede más del evento que el promedio (defensa floja). El producto captura
la interacción ataque-fuerte-vs-defensa-floja como una tasa inflada, y ataque-flojo-vs-defensa-
fuerte como una tasa reducida — sin necesitar una regresión completa cuando los datos son
escasos (early season) y sirviendo de prior informativo cuando sí se usa GLM/XGBoost encima.
"""
from __future__ import annotations


def attack_factor(team_for_rate: float, league_avg_for: float) -> float:
    if league_avg_for <= 0:
        return 1.0
    return team_for_rate / league_avg_for


def defense_factor(team_against_rate: float, league_avg_against: float) -> float:
    if league_avg_against <= 0:
        return 1.0
    return team_against_rate / league_avg_against


def expected_rate(league_avg: float, attack_i: float, defense_j: float) -> float:
    """λ esperado para el equipo i atacando contra la defensa del equipo j."""
    return max(league_avg * attack_i * defense_j, 1e-3)
