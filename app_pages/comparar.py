"""Comparador de dos jugadores en el mismo radar."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import similarity, viz

ctx = st.session_state["ctx"]
table = ctx["table"]
player, prow, display = ctx["player"], ctx["prow"], ctx["display"]
display_of, comp_label = ctx["display_of"], ctx["comp_label"]

ac.player_header(ctx)

sims = similarity.similar_players(table, player)
same_group = table[(table["position_group"] == prow["position_group"]) & (table["player"] != player)]
default_rival = sims.iloc[0]["player"] if not sims.empty else same_group.iloc[0]["player"]
rival_options = sorted(same_group["player"], key=lambda p: display_of[p])
rival = st.selectbox(
    "Comparar con",
    rival_options,
    index=rival_options.index(default_rival) if default_rival in rival_options else 0,
    format_func=display_of.get,
)
rrow = table[table["player"] == rival].iloc[0]

left, right = st.columns([3, 2])
with left:
    ac.fig_and_download(
        viz.radar_compare(prow, rrow, comp_label, display, display_of[rival]),
        "radar_comparado.png",
    )
with right:
    rp = ac.photo_of(display_of[rival])
    if rp:
        st.image(rp, width=90)
    rows = []
    for col_pct, label in viz.RADAR_METRICS.get(prow["position_group"], viz.RADAR_METRICS["MF"]):
        col_val = col_pct.removesuffix("_pct")
        rows.append(
            {
                "Métrica": label.replace("\n", " "),
                display: round(float(prow[col_val]), 2),
                f"p ({display.split()[-1]})": round(float(prow[col_pct])),
                display_of[rival]: round(float(rrow[col_val]), 2),
                f"p ({display_of[rival].split()[-1]})": round(float(rrow[col_pct])),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Valores per-90 y percentil (p) de cada jugador dentro del grupo posicional.")
