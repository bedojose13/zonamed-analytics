"""Generador de datos SINTÉTICOS para Zonamed Analytics.

IMPORTANTE: no existe aquí ningún dato real de la Liga BetPlay Dimayor, de árbitros ni de
jugadores. Los 20 equipos, estadios y altitudes son reales (dominio público), pero los
resultados, plantillas y estadísticas se generan con parámetros latentes aleatorios
(`TeamLatent`, `PlayerLatent`) para que el pipeline de features y el motor predictivo tengan
sobre qué entrenar y demostrar el flujo de punta a punta. En producción, este script se
reemplaza por un pipeline de ingestión real (proveedor de datos con licencia: Opta, StatsBomb,
Wyscout, API-Football, etc.) que llene las mismas tablas ORM.

Uso:
    python -m app.scripts.seed_db
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from app.core.database import init_db, session_scope
from app.services.player_aggregates import refresh_player_aggregates
from app.models import (
    Match,
    MatchCornerStats,
    MatchDisciplineStats,
    MatchStatus,
    Player,
    PlayerMatchStat,
    PlayerPosition,
    Referee,
    Rivalry,
    TacticalPosture,
    Team,
)

SEED = 20260812
TODAY = dt.date.today()  # ancla el calendario sintético a la fecha real de cuando se siembra la base

# (nombre, abreviatura, ciudad, estadio, altitud_m, temp_media_c, humedad_media_%)
DIMAYOR_TEAMS = [
    ("Atlético Nacional", "NAL", "Medellín", "Atanasio Girardot", 1495, 22, 65),
    ("Independiente Medellín", "DIM", "Medellín", "Atanasio Girardot", 1495, 22, 65),
    ("Millonarios FC", "MIL", "Bogotá", "El Campín", 2640, 14, 70),
    ("Independiente Santa Fe", "SFE", "Bogotá", "El Campín", 2640, 14, 70),
    ("América de Cali", "AME", "Cali", "Pascual Guerrero", 1000, 26, 60),
    ("Deportivo Cali", "DCA", "Cali", "Deportivo Cali", 1000, 26, 60),
    ("Junior de Barranquilla", "JUN", "Barranquilla", "Metropolitano", 18, 30, 75),
    ("Once Caldas", "ONC", "Manizales", "Palogrande", 2150, 17, 72),
    ("Deportes Tolima", "TOL", "Ibagué", "Manuel Murillo Toro", 1285, 27, 58),
    ("Atlético Bucaramanga", "ABU", "Bucaramanga", "Alfonso López", 959, 28, 55),
    ("Deportivo Pasto", "PAS", "Pasto", "Libertad", 2527, 14, 68),
    ("La Equidad", "EQU", "Bogotá", "Metropolitano de Techo", 2600, 14, 70),
    ("Fortaleza CEIF", "FOR", "Bogotá", "Metropolitano de Techo", 2600, 14, 70),
    ("Águilas Doradas", "AGU", "Rionegro", "Alberto Grisales", 2100, 18, 70),
    ("Envigado FC", "ENV", "Envigado", "Polideportivo Sur", 1650, 21, 66),
    ("Boyacá Chicó", "CHI", "Tunja", "La Independencia", 2820, 13, 65),
    ("Unión Magdalena", "UNM", "Santa Marta", "Sierra Nevada", 5, 31, 78),
    ("Alianza FC", "ALI", "Valledupar", "Armando Maestre", 168, 32, 60),
    ("Llaneros FC", "LLA", "Villavicencio", "Manuel Calle Lombana", 467, 29, 72),
    ("Cortuluá", "COR", "Tuluá", "18 de Marzo", 973, 25, 62),
]

REFEREE_NAMES = [
    "Wilmar Roldán", "Nicolás Gallo", "Andrés Rojas", "John Perdomo", "Carlos Ortega",
    "Ricardo García", "Ivo Méndez", "Diego Ulloa", "Iber Arias", "Deivis Salazar",
    "Kevin Castro", "Michael Gantiva", "Bismarck Santiago", "Hernán Delgado",
]

DERBY_PAIRS = [
    ("NAL", "DIM"),  # Clásico paisa
    ("MIL", "SFE"),  # Clásico bogotano
    ("AME", "DCA"),  # Clásico vallecaucano
]

FIRST_NAMES = [
    "Andrés", "Camilo", "Santiago", "Juan", "Carlos", "Kevin", "Yerson", "Jhon", "Deiber",
    "Marlon", "Rafael", "Sebastián", "Cristian", "Wilmar", "Daniel", "Elvis", "Jefferson",
    "Steven", "Brayan", "Miguel", "Fabián", "Yeison", "Duván", "Jorge", "Luis",
]
LAST_NAMES = [
    "Rodríguez", "Gómez", "Martínez", "Pérez", "García", "Hernández", "López", "Ramírez",
    "Torres", "Vargas", "Castro", "Rojas", "Morales", "Ortiz", "Suárez", "Muñoz", "Cárdenas",
    "Bonilla", "Quintero", "Zapata", "Mosquera", "Palacios", "Cuesta", "Arroyave",
]

POSITION_DISTRIBUTION = (
    [PlayerPosition.GK] * 2
    + [PlayerPosition.DF] * 6
    + [PlayerPosition.MF] * 6
    + [PlayerPosition.FW] * 4
)


@dataclass
class TeamLatent:
    """Parámetros ocultos que gobiernan la simulación (desconocidos por el motor predictivo,
    tal como en la realidad no conocemos la 'fuerza verdadera' de un equipo, solo la inferimos
    de datos observados)."""

    attack: float
    defense: float
    aggression: float
    wing_bias: float
    corner_volume: float


@dataclass
class PlayerLatent:
    aggression: float
    foul_drawing: float
    card_prone: float


def _rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


def seed_teams(db, rng: np.random.Generator) -> dict[str, Team]:
    teams: dict[str, Team] = {}
    for name, short, city, stadium, alt, temp, hum in DIMAYOR_TEAMS:
        team = Team(
            name=name, short_name=short, city=city, stadium=stadium,
            altitude_m=alt, avg_temperature_c=temp, avg_humidity_pct=hum,
        )
        db.add(team)
        teams[short] = team
    db.flush()
    return teams


def seed_rivalries(db, teams: dict[str, Team]) -> None:
    for a, b in DERBY_PAIRS:
        db.add(Rivalry(team_a_id=teams[a].id, team_b_id=teams[b].id, intensity_index=1.6,
                        label=f"Clásico {teams[a].city}"))


def seed_referees(db, rng: np.random.Generator) -> list[Referee]:
    referees = []
    for name in REFEREE_NAMES:
        avg_yellow = float(np.clip(rng.normal(3.8, 0.6), 2.2, 5.6))
        avg_red = float(np.clip(rng.normal(0.15, 0.06), 0.02, 0.4))
        ref = Referee(
            name=name,
            matches_officiated=0,
            avg_yellow_per_match=avg_yellow,
            avg_red_per_match=avg_red,
            avg_fouls_called_per_match=float(np.clip(rng.normal(23, 3), 15, 32)),
            strictness_index=round(avg_yellow / 3.8, 3),
        )
        db.add(ref)
        referees.append(ref)
    db.flush()
    return referees


def seed_players(db, teams: dict[str, Team], rng: np.random.Generator) -> dict[int, list[tuple[Player, PlayerLatent]]]:
    roster: dict[int, list[tuple[Player, PlayerLatent]]] = {}
    for team in teams.values():
        roster[team.id] = []
        for pos in POSITION_DISTRIBUTION:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            base_aggression = {
                PlayerPosition.GK: 0.2, PlayerPosition.DF: 1.3,
                PlayerPosition.MF: 1.1, PlayerPosition.FW: 0.7,
            }[pos]
            latent = PlayerLatent(
                aggression=float(np.clip(rng.normal(base_aggression, 0.25), 0.05, 2.2)),
                foul_drawing=float(np.clip(rng.normal(1.0, 0.3), 0.2, 2.0)),
                card_prone=float(np.clip(rng.normal(1.0, 0.35), 0.1, 2.5)),
            )
            player = Player(team_id=team.id, name=name, position=pos)
            db.add(player)
            roster[team.id].append((player, latent))
    db.flush()
    return roster


def _round_robin_schedule(short_names: list[str]) -> list[list[tuple[str, str]]]:
    """Método del círculo: N equipos -> N-1 jornadas de N/2 partidos cada una."""
    n = len(short_names)
    arr = short_names[1:]
    fixed = short_names[0]
    rounds = []
    for r in range(n - 1):
        ring = [fixed] + arr
        pairing = []
        for i in range(n // 2):
            home, away = ring[i], ring[n - 1 - i]
            if r % 2 == 1:
                home, away = away, home
            pairing.append((home, away))
        rounds.append(pairing)
        arr = [arr[-1]] + arr[:-1]
    return rounds


def _simulate_match(
    db, rng: np.random.Generator, matchday: int, kickoff: dt.datetime, status: MatchStatus,
    home: Team, away: Team, latent: dict[int, TeamLatent], referee: Referee,
    roster: dict[int, list[tuple[Player, PlayerLatent]]], rivalry_index: float,
) -> Match:
    home_latent, away_latent = latent[home.id], latent[away.id]

    home_rest = int(rng.integers(3, 11))
    away_rest = int(rng.integers(3, 11))
    away_travel_km = float(rng.uniform(50, 950))

    altitude_gap = max(0.0, home.altitude_m - away.altitude_m)
    fatigue_penalty = 1.0 + (altitude_gap / 3000.0) * 0.15 + max(0, (6 - away_rest)) * 0.02

    match = Match(
        home_team_id=home.id, away_team_id=away.id, referee_id=referee.id,
        matchday=matchday, kickoff=kickoff, status=status,
        venue_altitude_m=home.altitude_m, temperature_c=home.avg_temperature_c,
        humidity_pct=home.avg_humidity_pct, home_rest_days=home_rest, away_rest_days=away_rest,
        away_travel_km=away_travel_km,
    )
    db.add(match)
    db.flush()

    if status != MatchStatus.FINISHED:
        return match

    home_goal_rate = max(0.15, 1.35 * home_latent.attack / away_latent.defense * 1.12)
    away_goal_rate = max(0.10, 1.10 * away_latent.attack / home_latent.defense / fatigue_penalty)
    home_goals = int(rng.poisson(home_goal_rate))
    away_goals = int(rng.poisson(away_goal_rate))

    postures = list(TacticalPosture)
    home_posture = postures[int(rng.integers(0, len(postures)))]
    away_posture = postures[int(rng.integers(0, len(postures)))]

    home_corner_rate = 5.0 * home_latent.corner_volume * (0.85 + 0.3 * home_latent.wing_bias)
    away_corner_rate = 4.3 * away_latent.corner_volume * (0.85 + 0.3 * away_latent.wing_bias) / fatigue_penalty
    home_corners = int(rng.poisson(home_corner_rate))
    away_corners = int(rng.poisson(away_corner_rate))

    for team, is_home, corners, rate, latent_t, posture in (
        (home, True, home_corners, home_corner_rate, home_latent, home_posture),
        (away, False, away_corners, away_corner_rate, away_latent, away_posture),
    ):
        crosses_att = int(rng.poisson(18 * latent_t.wing_bias + 8))
        db.add(MatchCornerStats(
            match_id=match.id, team_id=team.id, is_home=is_home, corners_won=corners,
            crosses_attempted=crosses_att,
            crosses_completed=int(rng.binomial(crosses_att, 0.32)),
            shots_blocked_by_opponent=int(rng.poisson(3.5)),
            wing_play_index=round(float(np.clip(latent_t.wing_bias, 0, 1)), 3),
            possession_pct=round(float(np.clip(rng.normal(50, 8), 30, 70)), 1),
            tactical_posture=posture,
        ))

    referee_strictness = referee.strictness_index * (1.0 + 0.25 * (rivalry_index - 1.0))

    total_home_fouls = total_away_fouls = 0
    total_home_yellow = total_away_yellow = 0
    total_home_red = total_away_red = 0

    for team, is_home, opp_fatigue in ((home, True, 1.0), (away, False, fatigue_penalty)):
        squad = roster[team.id]
        involved_idx = rng.choice(len(squad), size=min(14, len(squad)), replace=False)
        team_fouls = team_yellow = team_red = 0
        for idx in involved_idx:
            player, plat = squad[int(idx)]
            minutes = int(rng.integers(20, 91))
            fouls = int(rng.poisson(0.55 * plat.aggression * opp_fatigue * (minutes / 90)))
            fouls_received = int(rng.poisson(0.5 * plat.foul_drawing * (minutes / 90)))
            booking_p = float(np.clip(0.07 * plat.card_prone * referee_strictness, 0.01, 0.6))
            yellow = bool(rng.random() < min(0.9, booking_p * (1 + 0.12 * fouls)))
            red = bool(yellow and rng.random() < 0.05 * referee.avg_red_per_match / 0.15)
            db.add(PlayerMatchStat(
                match_id=match.id, player_id=player.id, minutes_played=minutes,
                fouls_committed=fouls, fouls_received=fouls_received,
                yellow_card=yellow, red_card=red,
            ))
            team_fouls += fouls
            team_yellow += int(yellow)
            team_red += int(red)
        db.add(MatchDisciplineStats(
            match_id=match.id, team_id=team.id, is_home=is_home,
            fouls_committed=team_fouls, fouls_received=0,
            yellow_cards=team_yellow, red_cards=team_red,
            aggression_index=round(home_latent.aggression if is_home else away_latent.aggression, 3),
        ))
        if is_home:
            total_home_fouls, total_home_yellow, total_home_red = team_fouls, team_yellow, team_red
        else:
            total_away_fouls, total_away_yellow, total_away_red = team_fouls, team_yellow, team_red

    match.home_goals, match.away_goals = home_goals, away_goals
    match.home_corners, match.away_corners = home_corners, away_corners
    match.home_yellow_cards, match.away_yellow_cards = total_home_yellow, total_away_yellow
    match.home_red_cards, match.away_red_cards = total_home_red, total_away_red
    match.home_fouls, match.away_fouls = total_home_fouls, total_away_fouls
    referee.matches_officiated += 1
    return match


def run() -> None:
    init_db()
    rng = _rng()

    with session_scope() as db:
        teams = seed_teams(db, rng)
        seed_rivalries(db, teams)
        referees = seed_referees(db, rng)
        roster = seed_players(db, teams, rng)

        latent: dict[int, TeamLatent] = {}
        for short, team in teams.items():
            latent[team.id] = TeamLatent(
                attack=float(np.clip(rng.normal(1.0, 0.22), 0.5, 1.8)),
                defense=float(np.clip(rng.normal(1.0, 0.22), 0.5, 1.8)),
                aggression=float(np.clip(rng.normal(1.0, 0.2), 0.5, 1.8)),
                wing_bias=float(np.clip(rng.beta(2, 2), 0.05, 0.95)),
                corner_volume=float(np.clip(rng.normal(1.0, 0.2), 0.5, 1.7)),
            )

        rivalry_lookup = {frozenset(p): 1.6 for p in DERBY_PAIRS}

        short_names = list(teams.keys())
        schedule = _round_robin_schedule(short_names)  # 19 jornadas x 10 partidos

        last_finished_matchday = 15
        anchor_saturday = TODAY - dt.timedelta(days=(TODAY.weekday() - 5) % 7)  # último/próximo sábado
        # matchday `last_finished_matchday` cae en el sábado más reciente ya jugado
        base_date = anchor_saturday - dt.timedelta(days=7) if anchor_saturday >= TODAY else anchor_saturday

        for round_idx, pairing in enumerate(schedule, start=1):
            status = MatchStatus.FINISHED if round_idx <= last_finished_matchday else MatchStatus.SCHEDULED
            kickoff_date = base_date - dt.timedelta(weeks=(last_finished_matchday - round_idx)) if round_idx <= last_finished_matchday \
                else base_date + dt.timedelta(weeks=(round_idx - last_finished_matchday))
            kickoff = dt.datetime.combine(kickoff_date, dt.time(hour=20, minute=0))

            for slot, (home_short, away_short) in enumerate(pairing):
                referee = referees[int(rng.integers(0, len(referees)))]
                rivalry_index = rivalry_lookup.get(frozenset((home_short, away_short)), 1.0)
                match_kickoff = kickoff + dt.timedelta(hours=(slot % 3))
                _simulate_match(
                    db, rng, round_idx, match_kickoff, status,
                    teams[home_short], teams[away_short], latent, referee, roster, rivalry_index,
                )

        db.flush()
        refresh_player_aggregates(db)

    print("Seed completo: 20 equipos, 14 árbitros, plantillas y calendario (19 jornadas) generados.")


if __name__ == "__main__":
    run()
