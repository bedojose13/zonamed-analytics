"""Cliente experimental para la API pública NO OFICIAL de ESPN (sin key, sin límite de cuota
documentado, cubre la temporada EN CURSO — a diferencia de API-Football en el plan gratis).

No es una API oficial ni documentada por ESPN: puede cambiar o bloquearse sin aviso. Desde el
entorno de desarrollo (sandbox) da 403 (protección anti-bots), posiblemente por el rango de IP
de datacenter. Este módulo existe para probar si el servidor de Render (otra IP/región) sí
logra pasar ese bloqueo — ver GET /admin/test-espn en app/api/main.py.
"""
from __future__ import annotations

import httpx

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LEAGUE_SLUG = "col.1"  # Colombia - Primera A (Liga BetPlay Dimayor) en la nomenclatura de ESPN

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def test_connectivity() -> dict:
    """Prueba mínima: trae el scoreboard actual y reporta si se pudo conectar y cuántos eventos
    trajo, sin guardar nada — solo para diagnosticar si ESPN es alcanzable desde este servidor."""
    try:
        with httpx.Client(headers=_HEADERS, timeout=20.0) as client:
            resp = client.get(f"{BASE_URL}/{LEAGUE_SLUG}/scoreboard")
            resp.raise_for_status()
            data = resp.json()
        events = data.get("events", [])
        return {
            "ok": True,
            "status_code": resp.status_code,
            "league_name": (data.get("leagues") or [{}])[0].get("name"),
            "events_found": len(events),
            "sample": [
                {"date": e.get("date"), "name": e.get("name"),
                 "status": e.get("status", {}).get("type", {}).get("name")}
                for e in events[:5]
            ],
        }
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "status_code": exc.response.status_code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — endpoint de diagnóstico, cualquier falla se reporta tal cual
        return {"ok": False, "status_code": None, "error": str(exc)}
