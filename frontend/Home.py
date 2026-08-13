"""Punto de entrada de Streamlit — módulo 5 del brief.

Ejecutar (con la API corriendo en paralelo):
    streamlit run frontend/Home.py
"""
from __future__ import annotations

import streamlit as st

from api_client import api_is_up

st.set_page_config(page_title="Zonamed Analytics — BetPlay Dimayor", page_icon="⚽", layout="wide")

st.title("⚽ Zonamed Analytics")
st.subheader("Analítica y predicción probabilística — Liga BetPlay Dimayor")

if api_is_up():
    st.success("Conectado a la API de predicción.")
else:
    st.error(
        "No se pudo conectar con la API. Levántala con:\n\n"
        "`uvicorn app.api.main:app --reload --port 8000`"
    )

st.markdown(
    """
Usa el menú de la izquierda para navegar:

- **Próximos Partidos** — pronóstico pre-match: 1X2, córners y tarjetas probables.
- **Análisis Detallado** — radiografía completa de un partido: Monte Carlo, árbitro, clima y
  jugadores de riesgo disciplinario.
- **Partidos Jugados** — auditoría histórica: resultado real vs. proyectado.
    """
)
