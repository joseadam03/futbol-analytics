"""Encaje jugador–equipo: qué fichaje encaja con qué estilo, según los datos."""

import streamlit as st

from futbol_analytics import fit

ctx = st.session_state["ctx"]
table, events = ctx["table"], ctx["events"]
display_of = ctx["display_of"]

st.title("🧩 Encaje jugador–equipo")
st.caption(
    "Cruza el estilo de cada equipo (posesión, presión, verticalidad) con lo que cada "
    "jugador hace sobre el campo, y añade si mejora el nivel actual del puesto. "
    "Todo medido dentro de la competición cargada."
)

TEAM_COLS = {
    "team": "Equipo",
    "encaje": "Encaje",
    "estilo": "Estilo",
    "mejora_puesto": "Mejora del puesto",
    "posesion": "· posesión",
    "presion": "· presión",
    "verticalidad": "· verticalidad",
    "possession": "Posesión %",
    "ppda": "PPDA",
    "prog_share": "% pases prog.",
    "npxg_diff_pm": "npxG dif./p",
}
NUM = st.column_config.NumberColumn

tab_destinos, tab_fichajes = st.tabs(["Destinos para el jugador", "Fichajes para un equipo"])

with tab_destinos:
    st.markdown(f"#### ¿A qué equipos les encaja **{ctx['display']}**?")
    destinos = fit.teams_for_player(table, events, ctx["player"])

    view = destinos.copy()
    view["team"] = view["team"] + view["propio"].map({True: "  ← su equipo", False: ""})
    st.dataframe(
        view[list(TEAM_COLS)].rename(columns=TEAM_COLS),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Encaje": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Estilo": NUM(
                format="%+.2f", help="z_equipo · afinidad · z_jugador; >0 = hace lo que el estilo pide"
            ),
            "Mejora del puesto": NUM(
                format="%+.0f", help="Percentil del jugador − nivel actual del puesto en ese equipo"
            ),
            "· posesión": NUM(format="%+.2f"),
            "· presión": NUM(format="%+.2f"),
            "· verticalidad": NUM(format="%+.2f"),
            "Posesión %": NUM(format="%.1f"),
            "PPDA": NUM(format="%.1f", help="Más bajo = presión más intensa"),
            "% pases prog.": NUM(format="%.1f"),
            "npxG dif./p": NUM(format="%+.2f"),
        },
    )

    ajenos = destinos[~destinos["propio"]]
    if not ajenos.empty:
        top = ajenos.iloc[0]
        motivo = (
            "sobre todo por afinidad de **estilo**"
            if abs(top["estilo"]) >= abs(top["mejora_puesto"]) / 50
            else "sobre todo porque **mejora el nivel actual del puesto**"
        )
        st.markdown(
            f"**Lectura:** el mejor destino de {ctx['display']} sería **{top['team']}** "
            f"(encaje {top['encaje']:.0f}), {motivo}. El desglose por ejes indica qué parte "
            "del estilo del equipo casa con su perfil."
        )

with tab_fichajes:
    c_equipo, c_grupo = st.columns([3, 1])
    equipo = c_equipo.selectbox("Equipo que ficha", sorted(table["team"].unique()), key="fit_team")
    grupo = c_grupo.selectbox("Grupo posicional", ["Todos", "DF", "MF", "FW", "GK"], key="fit_group")

    fichajes = fit.players_for_team(table, events, equipo, None if grupo == "Todos" else grupo)
    fichajes["player"] = fichajes["player"].map(display_of).fillna(fichajes["player"])

    st.markdown(f"#### Mejores fichajes para **{equipo}** (top 15)")
    st.dataframe(
        fichajes.head(15)[
            [
                "player",
                "team",
                "primary_position",
                "minutes",
                "encaje",
                "estilo",
                "mejora_puesto",
                "npxg_p90",
                "xa_p90",
                "prog_passes_p90",
                "pressures_p90",
                "padj_tack_int_p90",
            ]
        ].rename(
            columns={
                "player": "Jugador",
                "team": "Equipo actual",
                "primary_position": "Posición",
                "minutes": "Minutos",
                "encaje": "Encaje",
                "estilo": "Estilo",
                "mejora_puesto": "Mejora del puesto",
                "npxg_p90": "npxG/90",
                "xa_p90": "xA/90",
                "prog_passes_p90": "Pases prog./90",
                "pressures_p90": "Presiones/90",
                "padj_tack_int_p90": "PAdj E+I/90",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Encaje": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Estilo": NUM(format="%+.2f"),
            "Mejora del puesto": NUM(format="%+.0f"),
            "Minutos": NUM(format="%.0f"),
            "npxG/90": NUM(format="%.2f"),
            "xA/90": NUM(format="%.2f"),
            "Pases prog./90": NUM(format="%.1f"),
            "Presiones/90": NUM(format="%.1f"),
            "PAdj E+I/90": NUM(format="%.1f"),
        },
    )

with st.expander("Cómo se calcula el encaje (y qué no dice)"):
    st.markdown(
        """
- **Estilo**: cada equipo se sitúa en tres ejes z-score dentro de la competición —
  posesión, presión (PPDA invertido + presiones por partido) y verticalidad (cuota
  de pases progresivos). Cada jugador, en sus métricas per-90 estandarizadas dentro
  de su grupo posicional. Una matriz de afinidad documentada en `fit.py` traduce
  cada eje en los rasgos que demanda; el componente de estilo es el producto
  `z_equipo · afinidad · z_jugador`.
- **Mejora del puesto**: percentil medio del jugador en las métricas clave de su
  grupo (las del radar) menos el nivel medio de los jugadores que el equipo ya
  tiene en ese grupo.
- **Encaje (0-100)**: percentil de la media de ambos componentes estandarizados
  dentro del conjunto comparado. Es un orden *dentro de esta competición*.
- **Lo que no dice**: nada de edad, precio, encaje táctico fino (rol exacto,
  perfil zurdo/diestro), química o contexto de club. En torneos cortos, además,
  el estilo de una selección son 3-7 partidos. Es una lente para ordenar
  candidatos, no un oráculo de fichajes.
"""
    )
