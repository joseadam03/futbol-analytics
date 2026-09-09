"""Comparador de hasta 5 jugadores en el mismo radar/gráfico de barras."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import narrative, similarity, viz

ctx = st.session_state["ctx"]
table = ctx["table"]
player, prow, display = ctx["player"], ctx["prow"], ctx["display"]
display_of, comp_label = ctx["display_of"], ctx["comp_label"]

ac.player_header(ctx)

sims = similarity.similar_players(table, player)
same_group = table[(table["position_group"] == prow["position_group"]) & (table["player"] != player)]
default_rival = None
if not sims.empty:
    default_rival = sims.iloc[0]["player"]
elif not same_group.empty:
    default_rival = same_group.iloc[0]["player"]
rival_options = sorted(same_group["player"], key=lambda p: display_of[p])
rivales = st.multiselect(
    "Comparar con (hasta 4 más)",
    rival_options,
    default=[default_rival] if default_rival in rival_options else [],
    format_func=display_of.get,
    max_selections=4,
    help=(
        "Con 3 o más jugadores en total, el radar superpuesto deja de leerse — a "
        "partir de ahí se cambia solo a barras agrupadas, mismo dato."
    ),
)

if not rivales:
    st.info("Elige al menos un jugador para comparar.")
    st.stop()

filas = [prow, *(table[table["player"] == r].iloc[0] for r in rivales)]
nombres = [display, *(display_of[r] for r in rivales)]

left, right = st.columns([3, 2])
with left:
    if len(filas) == 2:
        fig = viz.radar_compare(filas[0], filas[1], comp_label, nombres[0], nombres[1], ctx["pool_label"])
    else:
        fig = viz.multi_compare_chart(filas, nombres, comp_label, ctx["pool_label"])
    ac.fig_and_download(fig, "radar_comparado.png")
with right:
    if len(filas) == 2:
        rp = ac.photo_of(nombres[1])
        if rp:
            st.image(rp, width=90)
    rows = []
    for col_pct, label in viz.RADAR_METRICS.get(prow["position_group"], viz.RADAR_METRICS["MF"]):
        col_val = col_pct.removesuffix("_pct")
        fila = {"Métrica": label.replace("\n", " ")}
        for nombre, frow in zip(nombres, filas):
            fila[nombre] = round(float(frow[col_val]), 2)
            fila[f"p ({nombre.split()[-1]})"] = round(float(frow[col_pct]))
        rows.append(fila)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Valores per-90 y percentil (p) de cada jugador frente a los {ctx['pool_label']}.")
    with st.expander("Qué mide cada eje"):
        for col, label in viz.RADAR_METRICS.get(prow["position_group"], viz.RADAR_METRICS["MF"]):
            definicion = narrative.metric_definition(col)
            if definicion:
                st.markdown(f"- **{label.replace(chr(10), ' ')}** — {definicion}")
