"""Encaje jugador–equipo: qué fichaje encaja con qué estilo, según los datos."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import fit, viz

ctx = st.session_state["ctx"]
table, events = ctx["table"], ctx["events"]
display_of = ctx["display_of"]

st.title("🧩 Encaje jugador–equipo")
st.caption(
    "Cruza el estilo de cada equipo (posesión, presión, verticalidad) con lo que cada "
    "jugador hace sobre el campo, y añade si mejora el nivel actual del puesto — el rol "
    "fino cuando existe (un lateral no compite con un central), ponderado por minutos."
)

with st.expander("⚙️ Ajustes del modelo"):
    w_estilo = (
        st.slider(
            "Peso del estilo frente a la mejora del puesto",
            0,
            100,
            50,
            5,
            format="%d%%",
            help="0% = solo mejora del puesto; 100% = solo afinidad de estilo",
            key="fit_w_estilo",
        )
        / 100
    )
    c1, c2, c3 = st.columns(3)
    axis_weights = {
        "posesion": c1.slider("Eje posesión", 0.0, 2.0, 1.0, 0.1, key="fit_w_pos"),
        "presion": c2.slider("Eje presión", 0.0, 2.0, 1.0, 0.1, key="fit_w_pre"),
        "verticalidad": c3.slider("Eje verticalidad", 0.0, 2.0, 1.0, 0.1, key="fit_w_ver"),
    }
    st.caption(
        "Los pesos de los ejes multiplican su aporte al componente de estilo. La matriz "
        "de afinidad completa (qué rasgos demanda cada estilo) está documentada en `fit.py`."
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


def boton_csv(df: pd.DataFrame, filename: str, key: str) -> None:
    st.download_button(
        "⬇ CSV", df.to_csv(index=False).encode("utf-8"), file_name=filename, mime="text/csv", key=key
    )


tab_destinos, tab_fichajes = st.tabs(["Destinos para el jugador", "Fichajes para un equipo"])

with tab_destinos:
    st.markdown(f"#### ¿A qué equipos les encaja **{ctx['display']}**?")
    destinos = fit.teams_for_player(table, events, ctx["player"], w_estilo, axis_weights)

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
                format="%+.0f",
                help="Percentil del jugador − nivel del rol (o grupo) en ese equipo, ponderado por minutos",
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
    boton_csv(destinos, "encaje_destinos.csv", "csv_destinos")

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
            f"(encaje {top['encaje']:.0f}), {motivo}."
        )
        ac.fig_and_download(
            viz.style_map(
                fit.team_style(events),
                highlight=ajenos.head(3)["team"].tolist(),
                current_team=str(ctx["prow"]["team"]),
                subtitle=f"{ctx['comp_label']}  ·  mejores destinos de {ctx['display']}",
            ),
            "mapa_estilo.png",
        )

with tab_fichajes:
    c_equipo, c_grupo = st.columns([3, 1])
    equipo = c_equipo.selectbox("Equipo que ficha", sorted(table["team"].unique()), key="fit_team")
    grupo = c_grupo.selectbox("Grupo posicional", ["Todos", "DF", "MF", "FW", "GK"], key="fit_group")

    extra = ac.cached_competitions(ctx["provider_key"])
    extra_labels = [lb for lb in extra["label"] if lb != ctx["comp_label"]]
    pool_labels = st.multiselect(
        "Ampliar el pool con competiciones ya descargadas",
        extra_labels,
        key="fit_pool",
        help=(
            "Solo se ofrecen competiciones con los datos ya en caché. Los percentiles y "
            "z-scores de cada jugador se calculan dentro de su propia competición: comparar "
            "entre competiciones de nivel dispar es una aproximación."
        ),
    )

    pool = table
    if pool_labels:
        partes = [table.assign(competition=ctx["comp_label"])]
        for label in pool_labels:
            comp = extra[extra["label"] == label].iloc[0]
            extra_table = ac.build_table(
                ctx["provider_key"],
                int(comp["competition_id"]),
                int(comp["season_id"]),
                ctx["min_minutes"],
            )
            partes.append(extra_table.assign(competition=label))
        pool = pd.concat(partes, ignore_index=True)

    fichajes = fit.players_for_team(
        pool, events, equipo, None if grupo == "Todos" else grupo, w_estilo, axis_weights
    )
    if "nickname" in fichajes.columns:
        fichajes["player"] = (
            fichajes["player"].map(display_of).fillna(fichajes["nickname"]).fillna(fichajes["player"])
        )
    else:
        fichajes["player"] = fichajes["player"].map(display_of).fillna(fichajes["player"])

    st.markdown(f"#### Mejores fichajes para **{equipo}** (top 15)")
    cols = ["player", "team"]
    if "competition" in fichajes.columns:
        cols.append("competition")
    if "role" in fichajes.columns:
        cols.append("role")
    cols += [
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
    st.dataframe(
        fichajes.head(15)[cols].rename(
            columns={
                "player": "Jugador",
                "team": "Equipo actual",
                "competition": "Competición",
                "role": "Rol",
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
    boton_csv(fichajes, "encaje_fichajes.csv", "csv_fichajes")

with st.expander("Cómo se calcula el encaje (y qué no dice)"):
    st.markdown(
        """
- **Estilo**: cada equipo se sitúa en tres ejes z-score dentro de la competición —
  posesión, presión (PPDA invertido + presiones por partido) y verticalidad (cuota
  de pases progresivos). Cada jugador, en sus métricas per-90 estandarizadas dentro
  de su grupo posicional. Una matriz de afinidad documentada en `fit.py` traduce
  cada eje en los rasgos que demanda; el componente de estilo es el producto
  `z_equipo · afinidad · z_jugador`, con los pesos de eje del panel de ajustes.
- **Mejora del puesto**: percentil medio del jugador en las métricas clave de su
  grupo (las del radar) menos el nivel del puesto en el destino — la media de sus
  jugadores del mismo **rol fino** (lateral ≠ central) **ponderada por minutos**,
  con caída al grupo posicional cuando el equipo no tiene ese rol.
- **Encaje (0-100)**: percentil de la combinación ponderada de ambos componentes
  dentro del conjunto comparado. Es un orden *dentro del pool analizado*.
- **Pool multi-competición**: los percentiles y z-scores viajan con la competición
  de origen de cada jugador; el nivel entre competiciones no se corrige, así que
  el número entre ligas dispares es orientativo.
- **Lo que no dice**: nada de edad, precio, encaje táctico fino (perfil
  zurdo/diestro, rol exacto en el sistema), química o contexto de club. En torneos
  cortos, el estilo de una selección son 3-7 partidos. Es una lente para ordenar
  candidatos, no un oráculo de fichajes.
"""
    )
