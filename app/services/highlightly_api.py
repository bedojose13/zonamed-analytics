"""Cliente delgado para Highlightly (https://highlightly.net/football-api/documentation).

Reemplaza a API-Football como fuente de datos reales: a diferencia de API-Football, el plan
gratuito de Highlightly SÍ da acceso a la temporada en curso (confirmado en vivo: 394 partidos
de la temporada 2026 de la Primera A de Colombia, incluyendo partidos "Not started" reales),
además de estadísticas por partido (córners, faltas, tarjetas, posesión, xG) en el mismo plan
gratuito de 100 llamadas/día.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings

settings = get_settings()


class HighlightlyApiError(RuntimeError):
    pass


class HighlightlyApiClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.highlightly_api_key
        if not self.api_key:
            raise HighlightlyApiError(
                "Falta ZONAMED_HIGHLIGHTLY_API_KEY — consigue una key gratis en https://highlightly.net/dashboard"
            )
        self._client = httpx.Client(
            base_url="https://soccer.highlightly.net",
            headers={"x-rapidapi-key": self.api_key},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HighlightlyApiClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        resp = self._client.get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    def get_matches_page(self, league_id: int, season: int, limit: int = 100, offset: int = 0) -> dict:
        return self._get("/matches", {"leagueId": league_id, "season": season, "limit": limit, "offset": offset})

    def get_all_matches(self, league_id: int, season: int) -> list[dict]:
        """Trae TODAS las páginas — con ~400 partidos por temporada y limit=100, son ~4 llamadas."""
        all_matches: list[dict] = []
        offset = 0
        while True:
            page = self.get_matches_page(league_id, season, limit=100, offset=offset)
            rows = page.get("data", [])
            all_matches.extend(rows)
            total = page.get("pagination", {}).get("totalCount", len(all_matches))
            offset += len(rows)
            if not rows or offset >= total:
                break
        return all_matches

    def get_match_statistics(self, match_id: int) -> list[dict]:
        return self._get(f"/statistics/{match_id}")
