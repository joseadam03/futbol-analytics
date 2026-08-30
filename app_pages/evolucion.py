"""Evolución por jornada: cómo cambia el rendimiento a lo largo del calendario."""

import altair as alt
import streamlit as st

import app_common as ac
from futbol_analytics import series as sr

ctx = st.session_state["ctx"]

st.title("📈 Evolución por jornada")
st.caption(
    "Una media de temporada esconde las rachas. Aquí cada partido es un punto y la "
    "línea gruesa es la media móvil: el dato de un partido es ruido, la tendencia informa."
)

ts = ac.team_series_table(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
if ts.empty:
    st.info("No hay partidos suficientes para construir una serie temporal.")
    st.stop()

tab_equipo, tab_jugador = st.tabs(["Equipo", "Jugador"])
ink = "#0b0b0b" if ctx["theme"] == "light" else "#ffffff"
colores = ac.SCATTER_COLORS[ctx["theme"]]


def grafico_evolucion(df, metrica, etiqueta, color):
    """Puntos por partido + media móvil, sobre el eje de jornadas."""
    base = alt.Chart(df).encode(x=alt.X("partido:Q", title="Partido disputado", axis=alt.Axis(tickMinStep=1)))
    puntos = base.mark_circle(size=70, opacity=0.55, color=color).encode(
        y=alt.Y(f"{metrica}:Q", title=etiqueta),
        tooltip=[
            alt.Tooltip("partido:Q", title="Partido"),
            alt.Tooltip("jornada:Q", title="Jornada"),
            alt.Tooltip(f"{metrica}:Q", title=etiqueta, format=".2f"),
        ]
        + ([alt.Tooltip("opponent:N", title="Rival")] if "opponent" in df.columns else []),
    )
    linea = base.mark_line(strokeWidth=3, color=color).encode(y=alt.Y(f"{metrica}_roll:Q"))
    cero = alt.Chart(df).mark_rule(strokeDash=[4, 4], opacity=0.4).encode(y=alt.datum(0))
    return puntos + linea + cero


with tab_equipo:
    equipos = sorted(ts["team"].unique())
    propio = str(ctx["prow"]["team"])
    equipo = st.selectbox(
        "Equipo", equipos, index=equipos.index(propio) if propio in equipos else 0, key="evo_team"
    )
    metrica = st.selectbox(
        "Métrica",
        list(sr.TEAM_SERIES_METRICS),
        format_func=lambda m: sr.TEAM_SERIES_METRICS[m],
        key="evo_team_metric",
    )
    df = ts[ts["team"] == equipo].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Partidos", f"{len(df)}")
    c2.metric("npxG a favor (total)", f"{df['npxg_for'].sum():.2f}")
    c3.metric("npxG diferencia (total)", f"{df['npxg_diff'].sum():+.2f}")

    st.altair_chart(
        grafico_evolucion(df, metrica, sr.TEAM_SERIES_METRICS[metrica], colores[0]),
        use_container_width=True,
    )

    st.markdown("#### npxG acumulado a favor y en contra")
    acumulado = df.melt(
        id_vars=["partido"],
        value_vars=["npxg_for_cum", "npxg_against_cum"],
        var_name="serie",
        value_name="npxg",
    )
    acumulado["serie"] = acumulado["serie"].map({"npxg_for_cum": "A favor", "npxg_against_cum": "En contra"})
    st.altair_chart(
        alt.Chart(acumulado)
        .mark_line(strokeWidth=3)
        .encode(
            x=alt.X("partido:Q", title="Partido disputado", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("npxg:Q", title="npxG acumulado"),
            color=alt.Color(
                "serie:N",
                title=None,
                scale=alt.Scale(domain=["A favor", "En contra"], range=colores[:2]),
            ),
            tooltip=["partido", "serie", alt.Tooltip("npxg", format=".2f")],
        ),
        use_container_width=True,
    )
    st.caption(
        "Cuando la línea de *a favor* se separa hacia arriba, el equipo domina; si se "
        "cruzan, el momento en que cambió la temporada."
    )

    st.dataframe(
        df[["jornada", "opponent", "npxg_for", "npxg_against", "npxg_diff", "possession"]]
        .round(2)
        .rename(
            columns={
                "jornada": "Jornada",
                "opponent": "Rival",
                "npxg_for": "npxG a favor",
                "npxg_against": "npxG en contra",
                "npxg_diff": "npxG dif.",
                "possession": "Posesión %",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

with tab_jugador:
    ps = ac.player_series_table(
        ctx["provider_key"],
        int(ctx["comp"]["competition_id"]),
        int(ctx["comp"]["season_id"]),
        ctx["player"],
    )
    if ps.empty:
        st.info(f"No hay eventos de {ctx['display']} para construir su serie.")
    else:
        metrica_j = st.selectbox(
            "Métrica",
            list(sr.PLAYER_SERIES_METRICS),
            format_func=lambda m: sr.PLAYER_SERIES_METRICS[m],
            key="evo_player_metric",
        )
        st.markdown(f"#### {ctx['display']} · {sr.PLAYER_SERIES_METRICS[metrica_j]} por partido")
        st.altair_chart(
            grafico_evolucion(ps, metrica_j, sr.PLAYER_SERIES_METRICS[metrica_j], colores[1]),
            use_container_width=True,
        )
        c1, c2 = st.columns(2)
        c1.metric("Partidos con eventos", f"{len(ps)}")
        c2.metric("npxG acumulado", f"{ps['npxg'].sum():.2f}")
        st.caption(
            "La media móvil usa una ventana de 5 partidos; con menos partidos disputados "
            "se calcula con los que haya."
        )
