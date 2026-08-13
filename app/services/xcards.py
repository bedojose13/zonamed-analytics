"""Expected Cards / Fouls (xCards): módulo 2 del brief.

Lógica matemática
------------------
1) Tasa base de faltas: igual que en xC, se combinan `fouls_for` de un equipo y `fouls_against`
   del rival mediante el modelo ataque/defensa multiplicativo (app/services/rate_model.py)
   sobre el promedio de liga, para obtener `expected_fouls` por equipo en el partido.

2) Conversión falta -> tarjeta: no todas las faltas terminan en tarjeta; la tasa de conversión
   depende fuertemente del árbitro. Se modela como:

        expected_cards_team = expected_fouls_team * p_card_given_foul * strictness_ref * h2h_mult

   donde:
   - `p_card_given_foul` es la tasa histórica liga-wide de tarjetas por falta (constante).
   - `strictness_ref` = avg_yellow_per_match(árbitro) / avg_yellow_per_match(liga) — un árbitro
     33% más estricto que el promedio multiplica la probabilidad de tarjeta por 1.33.
   - `h2h_mult` combina la intensidad estática del derbi (`Rivalry.intensity_index`) con la
     intensidad dinámica observada (tarjetas promedio en los enfrentamientos directos vs.
     tarjetas promedio de cada equipo en general) — un derbi con historial de partidos trabados
     eleva la expectativa de tarjetas incluso si el árbitro no es especialmente estricto.

Esto separa explícitamente "cuántas faltas va a haber" (función del estilo de los equipos) de
"cuántas de esas faltas se castigan" (función del árbitro), que es la relación causal real del
fenómeno y por eso generaliza mejor que una regresión ciega sobre tarjetas históricas.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Referee, Rivalry
from app.services import rate_model
from app.services.league_baseline import load_league_averages
from app.services.team_history import get_h2h_matches, get_recent_matches
from app.services.weighting import exponential_weighted_average


def _p_card_given_foul() -> float:
    avg = load_league_averages()
    return avg.yellow_per_match / (2 * avg.fouls_for)  # tarjetas de liga / faltas totales por equipo


@dataclass
class DisciplineRates:
    fouls_for: float
    fouls_against: float
    cards_for: float


def compute_team_discipline_rates(db: Session, team_id: int, before_match_id: int | None = None) -> DisciplineRates:
    obs = get_recent_matches(db, team_id, before_match_id=before_match_id, require_full_stats=True)
    if not obs:
        avg = load_league_averages()
        return DisciplineRates(avg.fouls_for, avg.fouls_for, avg.yellow_per_match / 2)
    return DisciplineRates(
        fouls_for=exponential_weighted_average([o.fouls_for for o in obs]),
        fouls_against=exponential_weighted_average([o.fouls_against for o in obs]),
        cards_for=exponential_weighted_average([o.cards_for for o in obs]),
    )


def referee_strictness(referee: Referee | None) -> float:
    if referee is None:
        return 1.0
    return referee.avg_yellow_per_match / load_league_averages().yellow_per_match


def h2h_intensity_multiplier(db: Session, team_a_id: int, team_b_id: int, static_rivalry: Rivalry | None) -> float:
    static_index = static_rivalry.intensity_index if static_rivalry else 1.0

    h2h_matches = get_h2h_matches(db, team_a_id, team_b_id, limit=6)
    if len(h2h_matches) < 2:
        return static_index

    total_cards = [
        (m.home_yellow_cards or 0) + (m.away_yellow_cards or 0)
        + (m.home_red_cards or 0) + (m.away_red_cards or 0)
        for m in h2h_matches
    ]
    h2h_avg = sum(total_cards) / len(total_cards)
    dynamic_index = h2h_avg / (2 * load_league_averages().yellow_per_match)
    return float(min(2.2, max(static_index, dynamic_index)))


def expected_match_fouls(home_rates: DisciplineRates, away_rates: DisciplineRates) -> tuple[float, float]:
    league_avg = load_league_averages().fouls_for
    home_attack = rate_model.attack_factor(home_rates.fouls_for, league_avg)
    away_defense = rate_model.defense_factor(away_rates.fouls_against, league_avg)
    away_attack = rate_model.attack_factor(away_rates.fouls_for, league_avg)
    home_defense = rate_model.defense_factor(home_rates.fouls_against, league_avg)

    expected_home = rate_model.expected_rate(league_avg, home_attack, away_defense)
    expected_away = rate_model.expected_rate(league_avg, away_attack, home_defense)
    return float(expected_home), float(expected_away)


def expected_match_cards(
    expected_home_fouls: float, expected_away_fouls: float,
    referee: Referee | None, h2h_mult: float,
) -> tuple[float, float]:
    strictness = referee_strictness(referee)
    p_card_given_foul = _p_card_given_foul()
    home_cards = expected_home_fouls * p_card_given_foul * strictness * h2h_mult
    away_cards = expected_away_fouls * p_card_given_foul * strictness * h2h_mult
    return float(home_cards), float(away_cards)
