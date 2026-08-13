"""Ingesta de datos REALES de la Liga BetPlay Dimayor vía API-Football (plan gratuito, temporada
2024 — el plan free no cubre la temporada en curso, ver conversación/README).

Es idempotente y resumible: se puede (y se debe) volver a correr muchas veces; cada corrida
retoma donde quedó la anterior sin gastar de más el cupo diario de 100 llamadas del plan free
(ver app/services/sync_state.py). Diseñado para llamarse en cada arranque del proceso (Render
free tier reinicia el proceso cada vez que el servicio despierta de dormir) y/o desde un cron
externo gratuito que golpee POST /admin/sync una vez al día (ver DEPLOY.md).

Uso manual:
    python -m app.scripts.sync_real_data
"""
from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import init_db, session_scope
from app.models import Match, MatchCornerStats, MatchDisciplineStats, MatchStatus, Referee, Rivalry, Team
from app.services.football_api import FootballApiClient
from app.services.sync_state import BudgetExhausted, CallBudget, mark_fixtures_synced, mark_teams_synced

settings = get_settings()

# Clásicos reales conocidos de la Dimayor — se emparejan por substring del nombre real de la API
# (sin costo de API, pura lógica local). Alimenta el multiplicador H2H de app/services/xcards.py.
# Los fragmentos deben ser lo bastante específicos para no matchear otro club por accidente
# (p. ej. "nacional" también aparece dentro de "Internacional de Bogotá").
KNOWN_DERBIES = [
    ("atleticonacional", "medellin", 1.6, "Clásico Paisa"),
    ("millonarios", "santafe", 1.6, "Clásico Bogotano"),
    ("america", "deportivocali", 1.5, "Clásico Vallecaucano"),
]

_STATUS_MAP = {
    "FT": MatchStatus.FINISHED, "AET": MatchStatus.FINISHED, "PEN": MatchStatus.FINISHED,
    "AWD": MatchStatus.FINISHED, "WO": MatchStatus.FINISHED,
    "NS": MatchStatus.SCHEDULED, "TBD": MatchStatus.SCHEDULED,
    "PST": MatchStatus.POSTPONED, "CANC": MatchStatus.POSTPONED, "ABD": MatchStatus.POSTPONED,
}


def _normalize(name: str) -> str:
    """minúsculas + sin tildes/diacríticos + solo alfanumérico, para comparar nombres de equipo
    entre fuentes que no siempre acentúan igual ('Medellín' vs 'Medellin')."""
    nfkd = unicodedata.normalize("NFKD", name.lower())
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", ascii_only)


def _match_geo_reference(api_team_name: str) -> tuple[str, str, float, float, float]:
    """Empareja el nombre de equipo de la API contra nuestra lista curada de ciudad/altitud/clima
    (mismos 20 clubes reales usados antes en el seed sintético). Si no hay match, usa valores
    genéricos razonables en vez de fallar."""
    from app.scripts.seed_db import DIMAYOR_TEAMS

    norm_api = _normalize(api_team_name)
    for name, short, city, stadium, alt, temp, hum in DIMAYOR_TEAMS:
        norm_ref = _normalize(name)
        if norm_api in norm_ref or norm_ref in norm_api:
            return city, stadium, float(alt), float(temp), float(hum)
    # también probar por ciudad/alias comunes no cubiertos por substring directo
    return "Colombia", api_team_name, 1000.0, 24.0, 65.0


def sync_teams(db: Session, client: FootballApiClient, budget: CallBudget) -> None:
    budget.use(1)
    teams = client.get_teams(settings.football_league_id, settings.football_season)
    for t in teams:
        external_id = t["id"]
        existing = db.execute(select(Team).where(Team.external_id == external_id)).scalars().first()
        city, stadium, altitude, temp, humidity = _match_geo_reference(t["name"])
        venue = t.get("venue") or {}
        if existing is None:
            db.add(Team(
                external_id=external_id, name=t["name"], short_name=(t.get("code") or t["name"][:10]),
                city=venue.get("city") or city, stadium=venue.get("name") or stadium,
                altitude_m=altitude, avg_temperature_c=temp, avg_humidity_pct=humidity,
            ))
    db.commit()
    mark_teams_synced(db)
    print(f"[sync] Equipos sincronizados: {len(teams)}")
    sync_rivalries(db)


def sync_rivalries(db: Session) -> None:
    all_teams = db.execute(select(Team)).scalars().all()
    for frag_a, frag_b, intensity, label in KNOWN_DERBIES:
        team_a = next((t for t in all_teams if frag_a in _normalize(t.name)), None)
        team_b = next((t for t in all_teams if frag_b in _normalize(t.name) and t is not team_a), None)
        if team_a is None or team_b is None:
            continue
        existing = db.execute(select(Rivalry).where(
            ((Rivalry.team_a_id == team_a.id) & (Rivalry.team_b_id == team_b.id))
            | ((Rivalry.team_a_id == team_b.id) & (Rivalry.team_b_id == team_a.id))
        )).scalars().first()
        if existing is None:
            db.add(Rivalry(team_a_id=team_a.id, team_b_id=team_b.id, intensity_index=intensity, label=label))
    db.commit()


def _parse_matchday(round_label: str, fallback: int) -> int:
    m = re.search(r"(\d+)\s*$", round_label or "")
    return int(m.group(1)) if m else fallback


def _get_or_create_referee(db: Session, raw_name: str | None) -> Referee | None:
    if not raw_name:
        return None
    clean_name = raw_name.split(",")[0].strip()
    if not clean_name:
        return None
    ref = db.execute(select(Referee).where(Referee.name == clean_name)).scalars().first()
    if ref is None:
        ref = Referee(name=clean_name)
        db.add(ref)
        db.flush()
    return ref


def sync_fixtures(db: Session, client: FootballApiClient, budget: CallBudget) -> None:
    budget.use(1)
    fixtures = client.get_fixtures(settings.football_league_id, settings.football_season)
    team_by_external_id = {t.external_id: t for t in db.execute(select(Team)).scalars().all() if t.external_id}

    for idx, fx in enumerate(fixtures, start=1):
        external_id = fx["fixture"]["id"]
        existing = db.execute(select(Match).where(Match.external_id == external_id)).scalars().first()
        if existing is not None:
            continue

        home = team_by_external_id.get(fx["teams"]["home"]["id"])
        away = team_by_external_id.get(fx["teams"]["away"]["id"])
        if home is None or away is None:
            continue  # equipo fuera de nuestro catálogo (raro); se omite el partido

        status_short = fx["fixture"]["status"]["short"]
        status = _STATUS_MAP.get(status_short, MatchStatus.SCHEDULED)
        kickoff = dt.datetime.fromisoformat(fx["fixture"]["date"]).astimezone(dt.timezone.utc).replace(tzinfo=None)
        referee = _get_or_create_referee(db, fx["fixture"].get("referee"))

        db.add(Match(
            external_id=external_id, home_team_id=home.id, away_team_id=away.id,
            referee_id=referee.id if referee else None,
            matchday=_parse_matchday(fx["league"].get("round", ""), idx),
            kickoff=kickoff, status=status,
            venue_altitude_m=home.altitude_m, temperature_c=home.avg_temperature_c,
            humidity_pct=home.avg_humidity_pct,
            home_goals=fx["goals"]["home"], away_goals=fx["goals"]["away"],
        ))
    db.commit()
    mark_fixtures_synced(db)
    print(f"[sync] Calendario sincronizado: {len(fixtures)} partidos.")


def _stat_value(stats_block: list[dict], stat_type: str) -> float:
    for row in stats_block:
        if row["type"] == stat_type:
            raw = row["value"]
            if raw is None:
                return 0.0
            if isinstance(raw, str):
                return float(raw.replace("%", "") or 0)
            return float(raw)
    return 0.0


SECONDS_BETWEEN_CALLS = 6.5  # el plan free limita a 10 llamadas/minuto además del cupo diario


def backfill_statistics(db: Session, client: FootballApiClient, budget: CallBudget) -> int:
    pending = db.execute(
        select(Match)
        .where(Match.status == MatchStatus.FINISHED, Match.stats_synced.is_(False), Match.external_id.is_not(None))
        .order_by(Match.kickoff.asc())
    ).scalars().all()

    synced_count = 0
    for i, match in enumerate(pending):
        if budget.remaining <= 0:
            break
        try:
            budget.use(1)
        except BudgetExhausted:
            break

        if i > 0:
            time.sleep(SECONDS_BETWEEN_CALLS)

        try:
            stats = client.get_fixture_statistics(match.external_id)
        except Exception as exc:  # noqa: BLE001 — probablemente rate-limit transitorio: NO se marca
            # como sincronizado (se reintenta en la próxima corrida) y se corta el resto de esta
            # corrida — seguir insistiendo de inmediato solo generaría más errores 429.
            print(f"[sync] Error trayendo estadísticas de fixture {match.external_id}, se reintentará "
                  f"en la próxima corrida: {exc}")
            break

        if len(stats) < 2:
            # Respuesta válida pero vacía: este fixture puntual no tiene estadísticas en la API
            # (pasa con algunos partidos antiguos/menores) — ahí sí se marca para no reintentar
            # por siempre.
            match.stats_synced = True
            db.commit()
            continue

        for block in stats:
            team_external_id = block["team"]["id"]
            is_home = team_external_id == match.home_team.external_id
            s = block["statistics"]
            corners = int(_stat_value(s, "Corner Kicks"))
            fouls = int(_stat_value(s, "Fouls"))
            yellow = int(_stat_value(s, "Yellow Cards"))
            red = int(_stat_value(s, "Red Cards"))
            possession = _stat_value(s, "Ball Possession")

            db.add(MatchCornerStats(
                match_id=match.id, team_id=(match.home_team_id if is_home else match.away_team_id),
                is_home=is_home, corners_won=corners, possession_pct=possession or 50.0,
            ))
            db.add(MatchDisciplineStats(
                match_id=match.id, team_id=(match.home_team_id if is_home else match.away_team_id),
                is_home=is_home, fouls_committed=fouls, yellow_cards=yellow, red_cards=red,
            ))

            if is_home:
                match.home_corners, match.home_fouls = corners, fouls
                match.home_yellow_cards, match.home_red_cards = yellow, red
            else:
                match.away_corners, match.away_fouls = corners, fouls
                match.away_yellow_cards, match.away_red_cards = yellow, red

        match.stats_synced = True
        db.commit()
        synced_count += 1

    print(f"[sync] Estadísticas traídas en esta corrida: {synced_count} partidos "
          f"(pendientes antes de esta corrida: {len(pending)}).")
    return synced_count


def compute_rest_days(db: Session) -> None:
    """Días de descanso desde el partido anterior de cada equipo — se calcula de nuestros propios
    datos, sin costo de API."""
    matches = db.execute(select(Match).order_by(Match.kickoff.asc())).scalars().all()
    last_played: dict[int, dt.datetime] = {}
    for m in matches:
        if m.home_team_id in last_played:
            m.home_rest_days = max(1, (m.kickoff - last_played[m.home_team_id]).days)
        if m.away_team_id in last_played:
            m.away_rest_days = max(1, (m.kickoff - last_played[m.away_team_id]).days)
        if m.status == MatchStatus.FINISHED:
            last_played[m.home_team_id] = m.kickoff
            last_played[m.away_team_id] = m.kickoff
    db.commit()


def refresh_referee_aggregates(db: Session) -> None:
    """Recalcula rigurosidad real de cada árbitro a partir de los partidos ya backfilled — se
    vuelve más precisa a medida que avanza el backfill diario, sin costo de API."""
    referees = db.execute(select(Referee)).scalars().all()
    for ref in referees:
        matches = db.execute(
            select(Match).where(Match.referee_id == ref.id, Match.stats_synced.is_(True))
        ).scalars().all()
        if not matches:
            continue
        n = len(matches)
        ref.matches_officiated = n
        ref.avg_yellow_per_match = sum((m.home_yellow_cards or 0) + (m.away_yellow_cards or 0) for m in matches) / n
        ref.avg_red_per_match = sum((m.home_red_cards or 0) + (m.away_red_cards or 0) for m in matches) / n
        ref.avg_fouls_called_per_match = sum((m.home_fouls or 0) + (m.away_fouls or 0) for m in matches) / n

    league_avg = sum(r.avg_yellow_per_match * r.matches_officiated for r in referees if r.matches_officiated) / \
        max(sum(r.matches_officiated for r in referees), 1)
    league_avg = league_avg or 3.8
    for ref in referees:
        if ref.matches_officiated:
            ref.strictness_index = round(ref.avg_yellow_per_match / league_avg, 3)
    db.commit()


def run(max_calls: int | None = None) -> None:
    init_db()
    with session_scope() as db:
        budget = CallBudget(db, max_calls or settings.football_calls_per_run)
        print(f"[sync] Presupuesto de llamadas restante hoy: {budget.remaining}")

        with FootballApiClient() as client:
            if not budget.state.teams_synced and budget.remaining > 0:
                sync_teams(db, client, budget)
            if not budget.state.fixtures_synced and budget.remaining > 0:
                sync_fixtures(db, client, budget)
            if budget.remaining > 0:
                backfill_statistics(db, client, budget)

        compute_rest_days(db)
        refresh_referee_aggregates(db)
    print("[sync] Corrida completa.")


if __name__ == "__main__":
    run()
