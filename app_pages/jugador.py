"""Informe de jugador: métricas, radar, mapas y similares."""

import streamlit as st

import app_common as ac
from futbol_analytics import similarity, viz

ctx = st.session_state["ctx"]
table, events = ctx["table"], ctx["events"]
player, prow, display = ctx["player"], ctx["prow"], ctx["display"]
display_of, comp_label = ctx["display_of"], ctx["comp_label"]

ac.player_header(ctx)

cols = st.columns(5)
for col, (label, value, pct) in zip(
    cols,
    [
        ("npxG/90", f"{prow['npxg_p90']:.2f}", prow["npxg_p90_pct"]),
        ("xA/90", f"{prow['xa_p90']:.2f}", prow["xa_p90_pct"]),
        ("Pases prog./90", f"{prow['prog_passes_p90']:.1f}", prow["prog_passes_p90_pct"]),
        ("Regates/90", f"{prow['dribbles_cmp_p90']:.1f}", prow["dribbles_cmp_p90_pct"]),
        ("PAdj Entr+Int/90", f"{prow['padj_tack_int_p90']:.1f}", prow["padj_tack_int_p90_pct"]),
    ],
):
    col.metric(label, value)
    col.caption(f"percentil {pct:.0f}")

tab_radar, tab_mapas, tab_similares = st.tabs(["Radar", "Mapas", "Similares"])

with tab_radar:
    left, right = st.columns([3, 2])
    with left:
        ac.fig_and_download(viz.radar_chart(prow, comp_label, display), "radar.png")
    with right:
        st.markdown("#### Lectura")
        group = prow["position_group"]
        st.markdown(
            f"Cada eje es el **percentil per-90 del jugador frente a los {group} "
            f"de la competición** con al menos {ctx['min_minutes']:.0f} minutos. "
            "Un 90 significa que supera al 90 % de sus pares posicionales."
        )
        st.markdown(
            "- Las métricas defensivas usan **PAdj** (ajuste por posesión).\n"
            "- **xA** enlaza cada pase clave con el xG del tiro que generó.\n"
            "- Penaltis excluidos de las métricas de tiro."
        )

with tab_mapas:
    m1, m2 = st.columns(2)
    with m1:
        ac.fig_and_download(viz.touch_heatmap(events, player, comp_label, display), "mapa_calor.png")
        ac.fig_and_download(viz.shot_map(events, player, comp_label, display), "mapa_tiros.png")
    with m2:
        ac.fig_and_download(viz.pass_map(events, player, comp_label, display), "mapa_pases.png")

with tab_similares:
    st.markdown(
        "Perfiles más parecidos por **similitud de coseno** sobre métricas per-90 "
        "estandarizadas dentro del grupo posicional: compara *a qué se dedica* el "
        "jugador, no su volumen bruto."
    )
    sims = similarity.similar_players(table, player)
    sims_view = sims.copy()
    sims_view.insert(0, "Foto", [ac.photo_of(display_of.get(p, p)) or "" for p in sims_view["player"]])
    sims_view["player"] = sims_view["player"].map(display_of)
    st.dataframe(
        sims_view.rename(
            columns={
                "player": "Jugador",
                "team": "Equipo",
                "primary_position": "Posición",
                "minutes": "Minutos",
                "similarity": "Similitud",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Foto": st.column_config.ImageColumn("", width="small"),
            "Minutos": st.column_config.NumberColumn(format="%.0f"),
            "Similitud": st.column_config.ProgressColumn(min_value=-1.0, max_value=1.0, format="%.3f"),
        },
    )
