"""Estilo y rendimiento por equipo: posesión, PPDA, npxG a favor/en contra."""

import altair as alt
import streamlit as st

import app_common as ac
from futbol_analytics.teams import team_metrics

ctx = st.session_state["ctx"]

st.title("Equipos")
st.caption(f"{ctx['comp_label']} · métricas por partido, sin tandas de penaltis")


@st.cache_data(show_spinner=False)
def _teams(provider_key: str, competition_id: int, season_id: int):
    events = ac.load_events(provider_key, competition_id, season_id)
    return team_metrics(events)


teams = _teams(ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"]))

st.markdown("#### Ranking por diferencia de npxG por partido")
view = teams.rename(
    columns={
        "team": "Equipo",
        "matches": "PJ",
        "possession": "Posesión %",
        "npxg_for_pm": "npxG a favor",
        "npxg_against_pm": "npxG en contra",
        "npxg_diff_pm": "npxG dif.",
        "goals_for": "GF",
        "goals_against": "GC",
        "ppda": "PPDA",
        "pressures_pm": "Presiones/partido",
        "shots_pm": "Tiros/partido",
    }
)
st.dataframe(
    view.round(2),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Posesión %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
        "npxG a favor": st.column_config.NumberColumn(format="%.2f"),
        "npxG en contra": st.column_config.NumberColumn(format="%.2f"),
        "npxG dif.": st.column_config.NumberColumn(format="%+.2f"),
    },
)
st.caption(
    "**PPDA** = pases que se permiten al rival en su zona de construcción por cada "
    "acción defensiva propia en campo contrario. Cuanto más bajo, más intensa es la presión."
)

st.markdown("#### Posesión vs. dominio")
color = ac.SCATTER_COLORS[ctx["theme"]][0]
ink = "#0b0b0b" if ctx["theme"] == "light" else "#ffffff"
base = alt.Chart(teams).encode(
    x=alt.X("possession", title="Posesión %", scale=alt.Scale(zero=False)),
    y=alt.Y("npxg_diff_pm", title="npxG dif. por partido"),
    tooltip=[
        alt.Tooltip("team", title="Equipo"),
        alt.Tooltip("possession", title="Posesión %", format=".1f"),
        alt.Tooltip("npxg_diff_pm", title="npxG dif./partido", format="+.2f"),
        alt.Tooltip("ppda", title="PPDA", format=".1f"),
    ],
)
points = base.mark_circle(size=120, opacity=0.8, color=color)
labels = base.mark_text(align="left", dx=8, fontSize=10, color=ink).encode(text="team")
rule = alt.Chart(teams).mark_rule(strokeDash=[4, 4], opacity=0.4).encode(y=alt.datum(0))
st.altair_chart(points + labels + rule, use_container_width=True)
st.caption(
    "Arriba a la izquierda: equipos que dominan sin necesitar el balón. "
    "Abajo a la derecha: mucha posesión con poco peligro generado."
)
