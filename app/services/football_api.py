"""Cliente delgado para API-Football (https://www.api-football.com/documentation-v3).

Solo implementa los 3 endpoints que necesita la ingesta real: equipos, calendario de partidos
y estadísticas por partido (córners/faltas/tarjetas). El plan gratuito limita a 100 llamadas al
día — cada llamada real se cuenta y se reporta a quien la usa (ver app/services/sync_state.py)
para poder repartir el backfill histórico en varios días sin exceder el cupo.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings

settings = get_settings()


class FootballApiError(RuntimeError):
    pass


class FootballApiClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.football_api_key
        self.base_url = base_url or settings.football_api_base_url
        if not self.api_key:
            raise FootballApiError(
                "Falta ZONAMED_FOOTBALL_API_KEY — consigue una key gratis en "
                "https://dashboard.api-football.com/register"
            )
        self._client = httpx.Client(
            base_url=self.base_url, headers={"x-apisports-key": self.api_key}, timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FootballApiClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: dict) -> dict:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            raise FootballApiError(f"API-Football error en {path}: {data['errors']}")
        return data

    def get_teams(self, league_id: int, season: int) -> list[dict]:
        data = self._get("/teams", {"league": league_id, "season": season})
        return [row["team"] | {"venue": row.get("venue")} for row in data["response"]]

    def get_fixtures(self, league_id: int, season: int) -> list[dict]:
        data = self._get("/fixtures", {"league": league_id, "season": season})
        return data["response"]

    def get_fixture_statistics(self, fixture_id: int) -> list[dict]:
        data = self._get("/fixtures/statistics", {"fixture": fixture_id})
        return data["response"]
