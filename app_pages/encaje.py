"""Encaje jugador–equipo: qué fichaje encaja con qué estilo, según los datos."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import fit, narrative, viz

PPDA_DEF = (
    "pases que se permiten al rival en su construcción por cada acción defensiva "
    "propia en campo contrario; más bajo = presión más intensa"
)


def _con_icono_realismo(texto: str) -> str:
    """Solo para mostrar en pantalla — el CSV exporta el texto plano de `fit.py`."""
    if texto.startswith("Sobrecualificado"):
        return f"⚠️ {texto}"
    if texto:
        return f"🔼 {texto}"
    return texto


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
    "realismo": "Realismo",
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
    view["realismo"] = view["realismo"].map(_con_icono_realismo)
    st.dataframe(
        view[list(TEAM_COLS)].rename(columns=TEAM_COLS),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Encaje": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Estilo": NUM(
                format="%+.2f",
                help=(
                    "Cuánto encaja su forma de jugar con el estilo de ese equipo: positivo si "
                    "hace mucho de lo que ese estilo pide (presión, progresión o fiabilidad con "
                    "el balón, según el caso) — no mide si es mejor jugador en términos absolutos"
                ),
            ),
            "Mejora del puesto": NUM(
                format="%+.0f",
                help=(
                    "Cuánto sube el nivel del puesto si ficha: percentil del jugador menos el "
                    "de quienes ya juegan ahí (mismo rol si hay datos, ponderado por minutos). "
                    "Positivo = refuerzo; muy alto, ver columna Realismo"
                ),
            ),
            "Realismo": st.column_config.TextColumn(
                help=(
                    "Aviso cuando el salto de nivel es tan grande que, en la práctica, sería un "
                    "fichaje inusual o improbable (sueldo, ambición o nivel de competición no "
                    "están en los datos, así que no se inventan — solo se avisa)"
                )
            ),
            "· posesión": NUM(
                format="%+.2f",
                help="Suma si el equipo tiene mucha posesión y el jugador es fiable/progresivo con el balón",
            ),
            "· presión": NUM(
                format="%+.2f", help="Suma si el equipo presiona mucho y el jugador presiona/recupera balones"
            ),
            "· verticalidad": NUM(
                format="%+.2f",
                help="Suma si el equipo juega directo y el jugador conduce, regatea o llega al área",
            ),
            "Posesión %": NUM(format="%.1f"),
            "PPDA": NUM(format="%.1f", help=PPDA_DEF),
            "% pases prog.": NUM(
                format="%.1f",
                help="Pases que avanzan el balón hacia la portería rival, sobre el total de pases completados",
            ),
            "npxG dif./p": NUM(
                format="%+.2f",
                help="Goles esperados (sin penaltis) a favor menos en contra, por partido: cuánto domina el marcador esperado",
            ),
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
        aviso = ""
        if top["realismo"].startswith("Sobrecualificado"):
            aviso = (
                f" Ojo: el nivel de {ctx['display']} está tan por encima de la plantilla actual "
                "que, en la práctica, sería un fichaje improbable — aparece igual en la lista, "
                "pero tenlo en cuenta."
            )
        st.markdown(
            f"**Lectura:** el mejor destino de {ctx['display']} sería **{top['team']}** "
            f"(encaje {top['encaje']:.0f}), {motivo}.{aviso}"
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
    c_equipo, c_grupo, c_maxmin = st.columns([3, 1, 1.3])
    equipo = c_equipo.selectbox("Equipo que ficha", sorted(table["team"].unique()), key="fit_team")
    grupo = c_grupo.selectbox("Grupo posicional", ["Todos", "DF", "MF", "FW", "GK"], key="fit_group")
    max_minutos = c_maxmin.number_input(
        "Minutos máx.",
        min_value=0,
        value=0,
        step=100,
        key="fit_max_min",
        help=(
            "0 = sin límite. Útil para buscar suplentes o jugadores emergentes en vez de "
            "titulares consolidados — el mínimo ya lo fija el filtro de minutos de la barra lateral."
        ),
    )

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
                ctx["basis"],
            )
            partes.append(extra_table.assign(competition=label))
        pool = pd.concat(partes, ignore_index=True)

    ajustar = True
    if pool_labels:
        ajustar = st.checkbox(
            "Ajustar el nivel entre competiciones con jugadores puente",
            value=True,
            key="fit_adjust",
            help=(
                "Un percentil 80 no vale lo mismo en cada liga. Los jugadores presentes "
                "en dos competiciones sirven de puente: la mediana de su diferencia de "
                "nivel estima cuánto infla o desinfla cada una."
            ),
        )
        offsets = fit.competition_offsets(pool, ctx["comp_label"])
        for _, o in offsets.iterrows():
            if o["competition"] == ctx["comp_label"]:
                continue
            if o["bridged"]:
                st.caption(
                    f"**{o['competition']}**: {o['n_bridge']} jugadores puente · "
                    f"ajuste de nivel {o['offset']:+.1f} puntos de percentil."
                )
            else:
                st.warning(
                    f"**{o['competition']}**: solo {o['n_bridge']} jugadores en común con "
                    f"{ctx['comp_label']}, insuficientes para estimar el ajuste. Sus "
                    "percentiles se comparan sin corregir: trátalos como orientativos."
                )

    fichajes = fit.players_for_team(
        pool,
        events,
        equipo,
        None if grupo == "Todos" else grupo,
        w_estilo,
        axis_weights,
        adjust_level=ajustar,
    )
    if max_minutos > 0:
        fichajes = fichajes[fichajes["minutes"] <= max_minutos]
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
        "realismo",
        "npxg_p90",
        "xa_p90",
        "prog_passes_p90",
        "pressures_p90",
        "padj_tack_int_p90",
    ]
    RENAME_FICHAJES = {
        "player": "Jugador",
        "team": "Equipo actual",
        "competition": "Competición",
        "role": "Rol",
        "primary_position": "Posición",
        "minutes": "Minutos",
        "encaje": "Encaje",
        "estilo": "Estilo",
        "mejora_puesto": "Mejora del puesto",
        "realismo": "Realismo",
        "npxg_p90": "npxG/90",
        "xa_p90": "xA/90",
        "prog_passes_p90": "Pases prog./90",
        "pressures_p90": "Presiones/90",
        "padj_tack_int_p90": "PAdj E+I/90",
    }
    vista_fichajes = fichajes.head(15)[cols].copy()
    vista_fichajes["realismo"] = vista_fichajes["realismo"].map(_con_icono_realismo)
    st.dataframe(
        vista_fichajes.rename(columns=RENAME_FICHAJES),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Encaje": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Estilo": NUM(
                format="%+.2f",
                help=(
                    "Cuánto encaja su forma de jugar con el estilo de este equipo: positivo si "
                    "hace mucho de lo que ese estilo pide — no mide si es mejor jugador en "
                    "términos absolutos"
                ),
            ),
            "Mejora del puesto": NUM(
                format="%+.0f",
                help=(
                    "Cuánto sube el nivel del puesto si ficha: percentil del jugador menos el "
                    "de quienes ya juegan ahí. Muy alto → ver columna Realismo"
                ),
            ),
            "Realismo": st.column_config.TextColumn(
                help=(
                    "Aviso cuando el salto de nivel es tan grande que, en la práctica, sería un "
                    "fichaje inusual o improbable (sueldo, ambición, nivel de competición: no "
                    "están en los datos, así que no se inventan)"
                )
            ),
            "Minutos": NUM(format="%.0f"),
            "npxG/90": NUM(format="%.2f", help=narrative.metric_definition("npxg_p90")),
            "xA/90": NUM(format="%.2f", help=narrative.metric_definition("xa_p90")),
            "Pases prog./90": NUM(format="%.1f", help=narrative.metric_definition("prog_passes_p90")),
            "Presiones/90": NUM(format="%.1f", help=narrative.metric_definition("pressures_p90")),
            "PAdj E+I/90": NUM(format="%.1f", help=narrative.metric_definition("padj_tack_int_p90")),
        },
    )
    boton_csv(fichajes, "encaje_fichajes.csv", "csv_fichajes")

    if not fichajes.empty:
        top_f = fichajes.iloc[0]
        motivo_f = (
            "sobre todo por afinidad de **estilo**"
            if abs(top_f["estilo"]) >= abs(top_f["mejora_puesto"]) / 50
            else "sobre todo porque **mejora el nivel actual del puesto**"
        )
        aviso_f = ""
        if str(top_f["realismo"]).startswith("Sobrecualificado"):
            aviso_f = (
                f" Ojo: el nivel de {top_f['player']} está tan por encima de la plantilla "
                f"actual de {equipo} que, en la práctica, sería un fichaje improbable — "
                "aparece igual en la lista, pero tenlo en cuenta."
            )
        st.markdown(
            f"**Lectura:** el mejor fichaje para **{equipo}** sería **{top_f['player']}** "
            f"(encaje {top_f['encaje']:.0f}), {motivo_f}.{aviso_f}"
        )

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
- **Realismo**: como "mejora del puesto" no tiene techo, un jugador muy por encima
  del nivel de la plantilla sube el encaje sin límite — aunque en la práctica nadie
  ficha a alguien así de por medio sin que medien sueldo, ambición o nivel de
  competición (datos que no están aquí). Por encima de +25 puntos de percentil se
  etiqueta "Mejora clara"; por encima de +40, "Sobrecualificado — fichaje
  improbable en la práctica". La fila no se oculta ni se reordena, solo se avisa.
- **Pool multi-competición**: los percentiles y z-scores viajan con la competición
  de origen de cada jugador; el nivel entre competiciones no se corrige, así que
  el número entre ligas dispares es orientativo.
- **Lo que no dice**: nada de edad, precio, encaje táctico fino (perfil
  zurdo/diestro, rol exacto en el sistema), química o contexto de club. En torneos
  cortos, el estilo de una selección son 3-7 partidos. Es una lente para ordenar
  candidatos, no un oráculo de fichajes.
"""
    )
