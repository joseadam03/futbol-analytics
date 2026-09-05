"""Análisis de un partido: comparación de equipos, mapa de tiros y quién más destacó."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import narrative, series, teams, viz

ctx = st.session_state["ctx"]

st.title("🥅 Partido")

matches = ac.load_matches(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
if matches.empty or "home_team" not in matches.columns or "away_team" not in matches.columns:
    st.info(
        "Este proveedor no da el calendario con los equipos de cada partido, así que "
        "esta página no puede armar la comparación local-visitante."
    )
    st.stop()

matches = matches.copy()
if "match_date" in matches.columns:
    matches["_fecha"] = pd.to_datetime(matches["match_date"], errors="coerce")
    matches = matches.sort_values("_fecha")


def _etiqueta(row) -> str:
    partes = [f"{row.home_team} - {row.away_team}"]
    if "match_week" in matches.columns and pd.notna(getattr(row, "match_week", None)):
        partes.append(f"jornada {row.match_week:.0f}")
    fecha = getattr(row, "_fecha", None)
    if fecha is not None and pd.notna(fecha):
        partes.append(fecha.strftime("%d/%m/%Y"))
    return " · ".join(partes)


etiquetas = {int(row.match_id): _etiqueta(row) for row in matches.itertuples()}
match_id = st.selectbox("Partido", list(etiquetas), format_func=etiquetas.get, key="partido_sel")
partido = matches[matches["match_id"] == match_id].iloc[0]
home_team, away_team = str(partido["home_team"]), str(partido["away_team"])

resumen = teams.match_summary(ctx["events"], match_id)
equipos_con_datos = set(resumen["team"])
if resumen.empty or home_team not in equipos_con_datos or away_team not in equipos_con_datos:
    st.warning("No hay eventos suficientes de este partido en los datos cargados.")
    st.stop()

fila_local = resumen[resumen["team"] == home_team].iloc[0]
fila_visita = resumen[resumen["team"] == away_team].iloc[0]

st.markdown(f"## {home_team}  {fila_local['goals']:.0f} – {fila_visita['goals']:.0f}  {away_team}")
subtitulo = ctx["comp_label"]
if "match_week" in matches.columns and pd.notna(partido.get("match_week")):
    subtitulo += f" · jornada {partido['match_week']:.0f}"
st.caption(subtitulo)

st.markdown("#### Comparación")
tabla_cmp = pd.DataFrame(
    {
        "Métrica": ["Posesión %", "Tiros", "npxG", "Presiones"],
        home_team: [
            round(float(fila_local["possession"]), 1),
            int(fila_local["shots"]),
            round(float(fila_local["npxg"]), 2),
            int(fila_local["pressures"]),
        ],
        away_team: [
            round(float(fila_visita["possession"]), 1),
            int(fila_visita["shots"]),
            round(float(fila_visita["npxg"]), 2),
            int(fila_visita["pressures"]),
        ],
    }
)
st.dataframe(tabla_cmp, use_container_width=True, hide_index=True)
st.caption(
    "**Posesión** = porcentaje de los pases del partido que dio cada equipo. **npxG** "
    "= suma de la probabilidad de gol de cada tiro sin penaltis: mide las ocasiones "
    "creadas, no los goles reales, así que un equipo puede perder con más npxG que su "
    "rival sin que sea mala suerte — simplemente falló ocasiones más claras. "
    "**Presiones** = veces que un jugador fue a forzar la pérdida del balón rival."
)

st.markdown("#### Mapa de tiros")
ac.fig_and_download(
    viz.match_shot_map(ctx["events"], match_id, home_team, away_team, ctx["comp_label"]),
    "mapa_tiros_partido.png",
)
st.caption(
    f"Cada punto es un tiro sin penaltis: azul de {home_team}, naranja de {away_team}. "
    "Relleno = gol, hueco = sin gol. El tamaño indica el xG del tiro (más grande = "
    "ocasión más clara). Ambos ataques se muestran en el mismo campo, cada uno hacia "
    "su lado, para poder compararlos de un vistazo."
)

st.markdown("#### Quién más destacó")
jugadores = series.match_player_stats(ctx["events"], match_id)
if jugadores.empty:
    st.info("No hay eventos de jugadores para este partido.")
else:
    equipo_filtro = st.radio(
        "Equipo", ["Ambos", home_team, away_team], horizontal=True, key="partido_equipo_filtro"
    )
    vista = jugadores if equipo_filtro == "Ambos" else jugadores[jugadores["team"] == equipo_filtro]
    vista = vista.head(10)
    display_of = ctx["display_of"]
    tabla = vista.rename(
        columns={
            "player": "Jugador",
            "team": "Equipo",
            "goals": "Goles",
            "npxg": "npxG",
            "xa": "xA",
            "shots": "Tiros",
            "key_passes": "Pases clave",
            "prog_passes": "Pases progresivos",
            "impacto": "Impacto",
        }
    )
    tabla["Jugador"] = tabla["Jugador"].map(lambda p: display_of.get(p, p))
    st.dataframe(
        tabla[
            [
                "Jugador",
                "Equipo",
                "Goles",
                "npxG",
                "xA",
                "Tiros",
                "Pases clave",
                "Pases progresivos",
                "Impacto",
            ]
        ].round(2),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Ordenado por **Impacto**, de mayor a menor. Se muestran como mucho los 10 primeros.")
    with st.expander("Qué significa cada columna"):
        defs = [
            ("npxG", narrative.metric_definition("npxg_p90")),
            ("xA", narrative.metric_definition("xa_p90")),
            ("Tiros", narrative.metric_definition("shots_p90")),
            ("Pases clave", narrative.metric_definition("key_passes_p90")),
            ("Pases progresivos", narrative.metric_definition("prog_passes_p90")),
        ]
        for etiqueta, definicion in defs:
            if definicion:
                st.markdown(f"- **{etiqueta}** — {definicion}")
        st.markdown(
            "- **Impacto** — suma de goles + npxG + xA: una forma sencilla de ordenar "
            "quién generó más peligro en el partido, sumando lo que aportó con el "
            "remate y con el pase. No es una métrica oficial, es solo para ordenar esta tabla."
        )
