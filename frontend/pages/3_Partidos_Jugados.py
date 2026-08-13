from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import get_partidos_jugados

st.set_page_config(page_title="Partidos Jugados", page_icon="📊", layout="wide")
st.title("📊 Partidos Jugados — Real vs. Proyectado")

matchday = st.sidebar.number_input("Jornada (vacío = todas)", min_value=0, value=0, step=1)
matchday_filter = int(matchday) if matchday > 0 else None

try:
    partidos = get_partidos_jugados(matchday=matchday_filter)
except Exception as exc:  # noqa: BLE001
    st.error(f"No se pudo cargar el histórico: {exc}")
    st.stop()

if not partidos:
    st.info("Aún no hay partidos jugados con ese filtro.")
    st.stop()

df = pd.DataFrame(partidos)
df["partido"] = df["home_team"].apply(lambda t: t["short_name"]) + " vs " + df["away_team"].apply(lambda t: t["short_name"])
df["marcador_real"] = df["real_home_goals"].astype(str) + "-" + df["real_away_goals"].astype(str)

st.subheader("Panel comparativo: margen de acierto de la IA")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Partidos auditados", len(df))
col2.metric("Acierto de signo 1X2", f"{df['result_hit'].mean()*100:.1f}%")
col3.metric("Error medio de córners (MAE)", f"{df['corners_error_abs'].mean():.2f}")
col4.metric("Error medio de tarjetas (MAE)", f"{df['cards_error_abs'].mean():.2f}")

tab_tabla, tab_goles, tab_corners, tab_cards = st.tabs(["Tabla comparativa", "Goles", "Córners", "Tarjetas"])

with tab_tabla:
    display_cols = [
        "matchday", "partido", "marcador_real",
        "projected_home_goals", "projected_away_goals",
        "real_home_corners", "real_away_corners", "projected_home_corners", "projected_away_corners",
        "cards_error_abs", "result_hit",
    ]
    st.dataframe(df[display_cols].rename(columns={
        "matchday": "Jornada", "partido": "Partido", "marcador_real": "Marcador real",
        "projected_home_goals": "xG Local", "projected_away_goals": "xG Visita",
        "real_home_corners": "Córners Local (real)", "real_away_corners": "Córners Visita (real)",
        "projected_home_corners": "xCórners Local", "projected_away_corners": "xCórners Visita",
        "cards_error_abs": "Error tarjetas", "result_hit": "¿Acertó 1X2?",
    }), hide_index=True, use_container_width=True)

with tab_goles:
    df["real_total_goals"] = df["real_home_goals"] + df["real_away_goals"]
    df["proyectado_total_goals"] = df["projected_home_goals"] + df["projected_away_goals"]
    fig = px.scatter(df, x="proyectado_total_goals", y="real_total_goals", hover_name="partido",
                      title="Goles totales: proyectado vs. real (la diagonal = predicción perfecta)")
    fig.add_shape(type="line", x0=0, y0=0, x1=df["real_total_goals"].max() + 1, y1=df["real_total_goals"].max() + 1)
    st.plotly_chart(fig, use_container_width=True)

with tab_corners:
    df["real_total_corners"] = df["real_home_corners"] + df["real_away_corners"]
    df["proyectado_total_corners"] = df["projected_home_corners"] + df["projected_away_corners"]
    fig = px.scatter(df, x="proyectado_total_corners", y="real_total_corners", hover_name="partido",
                      title="Córners totales: proyectado vs. real")
    fig.add_shape(type="line", x0=0, y0=0, x1=df["real_total_corners"].max() + 1, y1=df["real_total_corners"].max() + 1)
    st.plotly_chart(fig, use_container_width=True)

with tab_cards:
    df["real_total_cards"] = (df["real_home_yellow_cards"] + df["real_away_yellow_cards"]
                               + df["real_home_red_cards"] + df["real_away_red_cards"])
    fig = px.scatter(df, x="projected_total_cards", y="real_total_cards", hover_name="partido",
                      title="Tarjetas totales: proyectado vs. real")
    fig.add_shape(type="line", x0=0, y0=0, x1=df["real_total_cards"].max() + 1, y1=df["real_total_cards"].max() + 1)
    st.plotly_chart(fig, use_container_width=True)
