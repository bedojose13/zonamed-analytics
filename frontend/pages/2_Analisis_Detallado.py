from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import get_analisis_detallado

st.set_page_config(page_title="Análisis Detallado", page_icon="🔬", layout="wide")
st.title("🔬 Análisis Detallado del Partido")

default_id = st.session_state.get("partido_id", 1)
partido_id = st.sidebar.number_input("ID de partido", min_value=1, value=int(default_id), step=1)
refresh = st.sidebar.checkbox("Forzar recálculo del motor (ignorar caché)", value=False)

try:
    data = get_analisis_detallado(int(partido_id), refresh=refresh)
except Exception as exc:  # noqa: BLE001
    st.error(f"No se pudo cargar el análisis: {exc}")
    st.stop()

home, away = data["home_team"], data["away_team"]
pred = data["prediction"]
mc = data["monte_carlo"]
weather = data["weather"]

st.markdown(f"### {home['name']} vs {away['name']} — Jornada {data['matchday']}")
if data["is_derby"]:
    st.warning(f"🔥 Partido de alta rivalidad — índice de intensidad H2H: {data['rivalry_intensity_index']:.2f}x")

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Altitud del estadio", f"{weather['venue_altitude_m']:.0f} m")
col_b.metric("Temperatura", f"{weather['temperature_c']:.0f} °C")
col_c.metric("Humedad", f"{weather['humidity_pct']:.0f} %")
col_d.metric("Descanso visitante", f"{weather['away_rest_days']} días")

st.divider()

st.subheader("Ficha de Predicción — Resultado y Marcador")
c1, c2, c3 = st.columns(3)
c1.metric(f"Gana {home['short_name']}", f"{pred['prob_home_win']*100:.1f}%")
c2.metric("Empate", f"{pred['prob_draw']*100:.1f}%")
c3.metric(f"Gana {away['short_name']}", f"{pred['prob_away_win']*100:.1f}%")

df_scores = pd.DataFrame(mc["top_scorelines"])
df_scores["marcador"] = df_scores["home_goals"].astype(str) + " - " + df_scores["away_goals"].astype(str)
fig_scores = px.bar(df_scores, x="marcador", y="probability", title="Marcadores más probables (Monte Carlo)",
                     labels={"probability": "Probabilidad", "marcador": "Marcador"})
st.plotly_chart(fig_scores, use_container_width=True)

st.divider()

col_corner, col_card = st.columns(2)

with col_corner:
    st.subheader("Ficha de Córners")
    st.metric(f"Línea de mercado", f"Más/Menos de {pred['corner_line_used']}")
    st.metric("Prob. Over", f"{pred['prob_over_corner_line']*100:.1f}%")
    df_corners = pd.DataFrame(mc["total_corners_distribution"].items(), columns=["córners_totales", "prob"])
    st.plotly_chart(px.bar(df_corners, x="córners_totales", y="prob", title="Distribución de córners totales"),
                     use_container_width=True)
    st.dataframe(pd.DataFrame(mc["corner_lines"]), hide_index=True, use_container_width=True)

with col_card:
    st.subheader("Ficha de Disciplina")
    st.metric(f"Línea de mercado", f"Más/Menos de {pred['card_line_used']}")
    st.metric("Prob. Over", f"{pred['prob_over_card_line']*100:.1f}%")
    st.metric("Prob. de al menos 1 tarjeta roja", f"{mc['prob_red_card_shown']*100:.1f}%")
    df_cards = pd.DataFrame(mc["total_cards_distribution"].items(), columns=["tarjetas_totales", "prob"])
    st.plotly_chart(px.bar(df_cards, x="tarjetas_totales", y="prob", title="Distribución de tarjetas totales"),
                     use_container_width=True)
    st.dataframe(pd.DataFrame(mc["card_lines"]), hide_index=True, use_container_width=True)

st.divider()
st.subheader("Jugadores con mayor riesgo de tarjeta")
df_risk = pd.DataFrame(data["discipline_risk_players"])
df_risk["Prob. de tarjeta (este partido) %"] = (df_risk["prob_booked"] * 100).round(1)
df_risk = df_risk.rename(columns={
    "player_name": "Jugador", "team_short_name": "Equipo", "card_proneness_index": "Índice histórico",
})
st.dataframe(
    df_risk[["Jugador", "Equipo", "Índice histórico", "Prob. de tarjeta (este partido) %"]],
    hide_index=True, use_container_width=True,
    column_config={"Prob. de tarjeta (este partido) %": st.column_config.ProgressColumn(
        format="%.1f%%", min_value=0, max_value=100)},
)

with st.expander("Ver JSON completo de la simulación Monte Carlo"):
    st.json(mc)
