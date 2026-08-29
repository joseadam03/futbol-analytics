"""Página de inicio: resumen de la competición y destacados."""

import streamlit as st

ctx = st.session_state["ctx"]
table = ctx["table"]
events = ctx["events"]

st.title("⚽ Fútbol Analytics")
st.caption(
    "Análisis de rendimiento de jugadores y equipos sobre datos de eventos. "
    "Elige competición y jugador en la barra lateral; cada página cuenta una parte de la historia."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Competición", ctx["comp_label"].split(" · ")[0])
c2.metric("Partidos", f"{events['match_id'].nunique()}")
c3.metric("Jugadores analizados", f"{len(table)}")
c4.metric("Equipos", f"{table['team'].nunique()}")

st.divider()

left, right = st.columns(2)
with left:
    st.markdown("#### Máximo peligro generado (npxG/90)")
    top = table.nlargest(5, "npxg_p90")[["nickname", "team", "npxg_p90"]]
    st.dataframe(
        top.rename(columns={"nickname": "Jugador", "team": "Equipo", "npxg_p90": "npxG/90"}),
        use_container_width=True,
        hide_index=True,
        column_config={"npxG/90": st.column_config.NumberColumn(format="%.2f")},
    )
with right:
    st.markdown("#### Máxima creación (xA/90)")
    top = table.nlargest(5, "xa_p90")[["nickname", "team", "xa_p90"]]
    st.dataframe(
        top.rename(columns={"nickname": "Jugador", "team": "Equipo", "xa_p90": "xA/90"}),
        use_container_width=True,
        hide_index=True,
        column_config={"xA/90": st.column_config.NumberColumn(format="%.2f")},
    )

st.divider()
st.markdown(
    """
**Cómo usar la app**

1. **Jugador** — informe completo: radar de percentiles, mapas de campo y perfiles similares.
2. **Comparar** — dos jugadores frente a frente en el mismo radar.
3. **Equipos** — estilo de juego: posesión, PPDA (intensidad de presión), npxG a favor y en contra.
4. **Competición** — dispersión interactiva de todos los jugadores y tabla completa descargable.

Cada gráfico tiene su botón de descarga en PNG para llevarlo a una presentación.
"""
)
