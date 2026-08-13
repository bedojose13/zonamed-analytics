from __future__ import annotations

import streamlit as st

from api_client import get_proximos_partidos

st.set_page_config(page_title="Próximos Partidos", page_icon="📅", layout="wide")
st.title("📅 Próximos Partidos — Análisis Pre-Match")

matchday = st.sidebar.number_input("Jornada (vacío = todas)", min_value=0, value=0, step=1)
matchday_filter = int(matchday) if matchday > 0 else None

try:
    partidos = get_proximos_partidos(matchday=matchday_filter)
except Exception as exc:  # noqa: BLE001 — mostrar cualquier error de conexión al usuario
    st.error(f"No se pudo cargar la lista de próximos partidos: {exc}")
    st.stop()

if not partidos:
    st.info("No hay partidos programados con ese filtro.")
    st.stop()

for p in partidos:
    pred = p.get("prediction")
    home, away = p["home_team"], p["away_team"]
    kickoff = p["kickoff"].replace("T", " ")[:16]

    with st.container(border=True):
        col_info, col_1x2, col_corners, col_cards = st.columns([2.2, 1.6, 1.3, 1.3])

        with col_info:
            st.markdown(f"**Jornada {p['matchday']}** · {kickoff}")
            st.markdown(f"### {home['short_name']} vs {away['short_name']}")
            st.caption(f"{home['stadium']} · {home['city']} ({home['altitude_m']:.0f} m) "
                       f"· Árbitro: {p['referee']['name'] if p['referee'] else 's/d'}")
            if st.button("Ver análisis detallado →", key=f"btn_{p['id']}"):
                st.session_state["partido_id"] = p["id"]
                st.switch_page("pages/2_Analisis_Detallado.py")

        if pred:
            with col_1x2:
                st.markdown("**Resultado (1X2)**")
                st.progress(pred["prob_home_win"], text=f"Local {pred['prob_home_win']*100:.0f}%")
                st.progress(pred["prob_draw"], text=f"Empate {pred['prob_draw']*100:.0f}%")
                st.progress(pred["prob_away_win"], text=f"Visita {pred['prob_away_win']*100:.0f}%")
                st.caption(f"Marcador más probable: **{pred['most_likely_score']}**")

            with col_corners:
                st.markdown("**Córners**")
                st.metric("Esperados (total)", f"{pred['expected_home_corners'] + pred['expected_away_corners']:.1f}")
                st.caption(f"Over {pred['corner_line_used']}: **{pred['prob_over_corner_line']*100:.0f}%**")

            with col_cards:
                st.markdown("**Tarjetas**")
                st.metric("Esperadas (total)", f"{pred['expected_home_cards'] + pred['expected_away_cards']:.1f}")
                st.caption(f"Over {pred['card_line_used']}: **{pred['prob_over_card_line']*100:.0f}%**")
                st.caption(f"P(roja mostrada): {pred['prob_red_card_shown']*100:.0f}%")
        else:
            st.warning("Predicción no disponible para este partido.")
