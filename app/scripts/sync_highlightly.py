"""Ingesta de datos REALES de la Liga BetPlay Dimayor vía Highlightly (temporada EN CURSO,
a diferencia de API-Football cuyo plan gratuito solo cubre 2022-2024 — ver conversación).

A diferencia del calendario (que SÍ cambia con el tiempo: partidos pasan de "Not started" a
"Finished" con marcador real), el calendario completo se re-trae en CADA corrida (son solo
~4 llamadas paginadas, barato) para mantener estados/marcadores al día. Las estadísticas por
partido (córners/faltas/tarjetas), en cambio, solo se traen UNA VEZ por partido ya finalizado
y se reparten en varios días respetando el cupo diario de 100 llamadas del plan gratuito — ver
app/services/sync_state.py.

Uso manual:
    python -m app.scripts.sync_highlightly
"""
from __future__ import annotations

import datetime as dt
import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import init_db, session_scope
from app.models import Match, MatchCornerStats, MatchDisciplineStats, MatchStatus, Referee, Team
from app.scripts.sync_real_data import _match_geo_reference, sync_rivalries
from app.services.highlightly_api import HighlightlyApiClient
from app.services.sync_state import BudgetExhausted, CallBudget, mark_fixtures_synced

settings = get_settings()

SECONDS_BETWEEN_STAT_CALLS = 3.0  # margen prudente; Highlightly no expuso límite por minuto en headers

_FINISHED = {"finished", "finished after penalties", "finished after extra time", "awarded"}
_LIVE = {"first half", "second half", "half time", "extra time", "break time", "penalties", "in progress"}
_POSTPONED = {"postponed", "suspended", "cancelled", "interrupted", "abandoned"}


def _map_status(description: str | None) -> MatchStatus:
    key = (description or "").strip().lower()
    if key in _FINISHED:
        return MatchStatus.FINISHED
    if key in _LIVE:
        return MatchStatus.LIVE
    if key in _POSTPONED:
        return MatchStatus.POSTPONED
    return MatchStatus.SCHEDULED


def _parse_score(score_current: str | None) -> tuple[int | None, int | None]:
    if not score_current:
        return None, None
    parts = score_current.split("-")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None, None


def _parse_matchday(round_label: str | None, fallback: int) -> int:
    m = re.search(r"(\d+)\s*$", round_label or "")
    return int(m.group(1)) if m else fallback


def _get_or_create_team(db: Session, external_id: int, name: str, teams_cache: dict[int, Team]) -> Team:
    if external_id in teams_cache:
        return teams_cache[external_id]
    team = db.execute(select(Team).where(Team.external_id == external_id)).scalars().first()
    if team is None:
        city, stadium, altitude, temp, humidity = _match_geo_reference(name)
        team = Team(
            external_id=external_id, name=name, short_name=name[:10],
            city=city, stadium=stadium, altitude_m=altitude,
            avg_temperature_c=temp, avg_humidity_pct=humidity,
        )
        db.add(team)
        db.flush()
    teams_cache[external_id] = team
    return team


def _get_or_create_referee(db: Session, raw_name: str | None) -> Referee | None:
    if not raw_name:
        return None
    clean_name = raw_name.strip()
    if not clean_name:
        return None
    ref = db.execute(select(Referee).where(Referee.name == clean_name)).scalars().first()
    if ref is None:
        ref = Referee(name=clean_name)
        db.add(ref)
        db.flush()
    return ref


def sync_matches(db: Session, client: HighlightlyApiClient, budget: CallBudget) -> None:
    teams_cache: dict[int, Team] = {}
    all_matches: list[dict] = []
    offset = 0
    while True:
        if budget.remaining <= 0:
            print("[sync] Presupuesto agotado a mitad de la paginación del calendario; se retoma en la próxima corrida.")
            break
        budget.use(1)
        page = client.get_matches_page(settings.highlightly_league_id, settings.highlightly_season,
                                        limit=100, offset=offset)
        rows = page.get("data", [])
        all_matches.extend(rows)
        total = page.get("pagination", {}).get("totalCount", len(all_matches))
        offset += len(rows)
        if not rows or offset >= total:
            break

    upserted = 0
    for idx, m in enumerate(all_matches, start=1):
        external_id = m["id"]
        home = _get_or_create_team(db, m["homeTeam"]["id"], m["homeTeam"]["name"], teams_cache)
        away = _get_or_create_team(db, m["awayTeam"]["id"], m["awayTeam"]["name"], teams_cache)
        referee = _get_or_create_referee(db, (m.get("referee") or {}).get("name"))

        status = _map_status(m.get("state", {}).get("description"))
        home_goals, away_goals = _parse_score((m.get("state", {}).get("score") or {}).get("current"))
        kickoff = dt.datetime.fromisoformat(m["date"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)

        match = db.execute(select(Match).where(Match.external_id == external_id)).scalars().first()
        if match is None:
            match = Match(
                external_id=external_id, home_team_id=home.id, away_team_id=away.id,
                matchday=_parse_matchday(m.get("round"), idx),
                venue_altitude_m=home.altitude_m, temperature_c=home.avg_temperature_c,
                humidity_pct=home.avg_humidity_pct,
            )
            db.add(match)
        match.referee_id = referee.id if referee else match.referee_id
        match.kickoff = kickoff
        match.status = status
        match.home_goals, match.away_goals = home_goals, away_goals
        upserted += 1

    db.commit()
    sync_rivalries(db)
    print(f"[sync] Calendario actualizado: {upserted} partidos procesados de {len(all_matches)} traídos.")
    if len(all_matches) >= 300:  # ya trajo prácticamente toda la temporada (~394 partidos totales)
        mark_fixtures_synced(db)


def _stat_value(stats_block: list[dict], display_name: str) -> float:
    for row in stats_block:
        if row.get("displayName") == display_name:
            return float(row.get("value") or 0)
    return 0.0


def backfill_statistics(db: Session, client: HighlightlyApiClient, budget: CallBudget) -> int:
    pending = db.execute(
        select(Match)
        .where(Match.status == MatchStatus.FINISHED, Match.stats_synced.is_(False), Match.external_id.is_not(None))
        .order_by(Match.kickoff.desc())  # los partidos más recientes primero: son los que más importan para forma reciente
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
            time.sleep(SECONDS_BETWEEN_STAT_CALLS)

        try:
            stats = client.get_match_statistics(match.external_id)
        except Exception as exc:  # noqa: BLE001 — se reintenta en la próxima corrida, no se marca sincronizado
            print(f"[sync] Error trayendo estadísticas de match {match.external_id}, se reintentará: {exc}")
            break

        if not isinstance(stats, list) or len(stats) < 2:
            match.stats_synced = True
            db.commit()
            continue

        for block in stats:
            team_external_id = block["team"]["id"]
            is_home = team_external_id == match.home_team.external_id
            s = block["statistics"]
            corners = int(_stat_value(s, "Corners"))
            fouls = int(_stat_value(s, "Fouls"))
            yellow = int(_stat_value(s, "Yellow cards"))
            red = int(_stat_value(s, "Red cards"))
            possession_pct = _stat_value(s, "Possession") * 100

            db.add(MatchCornerStats(
                match_id=match.id, team_id=(match.home_team_id if is_home else match.away_team_id),
                is_home=is_home, corners_won=corners, possession_pct=possession_pct or 50.0,
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


def refresh_referee_aggregates(db: Session) -> None:
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

    officiated_total = sum(r.matches_officiated for r in referees)
    league_avg = (sum(r.avg_yellow_per_match * r.matches_officiated for r in referees) / officiated_total
                  if officiated_total else 0.0) or 3.8
    for ref in referees:
        if ref.matches_officiated:
            ref.strictness_index = round(ref.avg_yellow_per_match / league_avg, 3)
    db.commit()


def compute_rest_days(db: Session) -> None:
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


def run(max_calls: int | None = None) -> None:
    init_db()
    with session_scope() as db:
        budget = CallBudget(db, max_calls or settings.highlightly_calls_per_run)
        print(f"[sync] Presupuesto de llamadas restante hoy: {budget.remaining}")

        with HighlightlyApiClient() as client:
            if budget.remaining > 0:
                sync_matches(db, client, budget)
            if budget.remaining > 0:
                backfill_statistics(db, client, budget)

        compute_rest_days(db)
        refresh_referee_aggregates(db)
    print("[sync] Corrida completa.")


if __name__ == "__main__":
    run()
