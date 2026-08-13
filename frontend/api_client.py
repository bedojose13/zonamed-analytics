"""Cliente HTTP delgado hacia la API FastAPI. Centraliza la URL base y el manejo de errores para
que las páginas de Streamlit no repitan lógica de requests."""
from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("ZONAMED_API_URL", "http://127.0.0.1:8000")


@st.cache_data(ttl=60)
def get_proximos_partidos(matchday: int | None = None, limit: int = 30) -> list[dict]:
    params = {"limit": limit}
    if matchday is not None:
        params["matchday"] = matchday
    resp = requests.get(f"{API_BASE_URL}/partidos/proximos", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60)
def get_analisis_detallado(partido_id: int, refresh: bool = False) -> dict:
    resp = requests.get(
        f"{API_BASE_URL}/partidos/analisis-detallado/{partido_id}",
        params={"refresh": refresh}, timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60)
def get_partidos_jugados(matchday: int | None = None, limit: int = 40) -> list[dict]:
    params = {"limit": limit}
    if matchday is not None:
        params["matchday"] = matchday
    resp = requests.get(f"{API_BASE_URL}/partidos/jugados", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_is_up() -> bool:
    try:
        r = requests.get(f"{API_BASE_URL}/", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False
