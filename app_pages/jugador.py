"""Informe de jugador: métricas, radar, mapas y similares."""

import streamlit as st

import app_common as ac
from futbol_analytics import narrative, similarity, viz

ctx = st.session_state["ctx"]
table, events = ctx["table"], ctx["events"]
player, prow, display = ctx["player"], ctx["prow"], ctx["display"]
display_of, comp_label = ctx["display_of"], ctx["comp_label"]

ac.player_header(ctx)

if st.button("🖨️ Generar informe-CV en PDF", key="btn_pdf"):
    with st.spinner("Componiendo el informe..."):
        pdf = ac.informe_pdf(
            ctx["provider_key"],
            int(ctx["comp"]["competition_id"]),
            int(ctx["comp"]["season_id"]),
            ctx["min_minutes"],
            player,
            comp_label,
            ctx["basis"],
        )
    st.download_button(
        "⬇ Descargar informe.pdf",
        pdf,
        file_name=f"informe_{display}.pdf",
        mime="application/pdf",
        key="dl_pdf",
    )

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
        ac.fig_and_download(viz.radar_chart(prow, comp_label, display, ctx["pool_label"]), "radar.png")
    with right:
        st.markdown("#### Lectura")
        resumen, fortalezas, debilidades = narrative.player_strengths(prow, ctx["pool_label"])
        if resumen:
            st.markdown(resumen)
        if fortalezas or debilidades:

            def _lista(rasgos: list[tuple[str, str]]) -> str:
                return "\n".join(
                    f"- **{titulo}**" + (f" — {definicion}" if definicion else "")
                    for titulo, definicion in rasgos
                )

            c_fort, c_flojo = st.columns(2)
            with c_fort:
                st.markdown("**Fortalezas**")
                st.markdown(_lista(fortalezas))
            with c_flojo:
                st.markdown("**Por mejorar**")
                st.markdown(_lista(debilidades))
        similar_texto = narrative.similar_players_note(similarity.similar_players(table, player))
        if similar_texto:
            st.caption(similar_texto)
        st.markdown(
            f"Cada eje es el **percentil per-90 del jugador frente a los {ctx['pool_label']} "
            f"de la competición** con al menos {ctx['min_minutes']:.0f} minutos. "
            "Un 90 significa que supera al 90 % de ese grupo."
        )
        if ctx["basis"] == "role" and prow.get("pct_basis") != "role":
            st.info(
                f"Hay menos de {ac.metrics.MIN_ROLE_SIZE} jugadores con el rol "
                f"**{prow.get('role')}**, así que la comparación cae a su grupo posicional."
            )
        st.markdown(
            "- Las métricas defensivas usan **PAdj** (ajuste por posesión).\n"
            "- **xA** enlaza cada pase clave con el xG del tiro que generó.\n"
            "- Penaltis excluidos de las métricas de tiro."
        )
        with st.expander("Qué mide cada eje del radar"):
            grupo = prow["position_group"]
            for col, label in viz.RADAR_METRICS.get(grupo, viz.RADAR_METRICS["MF"]):
                definicion = narrative.metric_definition(col)
                if definicion:
                    st.markdown(f"- **{label.replace(chr(10), ' ')}** — {definicion}")

with tab_mapas:
    m1, m2 = st.columns(2)
    with m1:
        ac.fig_and_download(viz.touch_heatmap(events, player, comp_label, display), "mapa_calor.png")
        st.caption(
            "**Mapa de calor**: dónde toca el balón más a menudo (pases, tiros, "
            "conducciones y controles). Más oscuro = más actividad en esa zona del campo."
        )
        ac.fig_and_download(viz.shot_map(events, player, comp_label, display), "mapa_tiros.png")
        st.caption(
            "**Mapa de tiros** (sin penaltis): punto relleno = gol, hueco = no gol. "
            "El tamaño es proporcional al **xG** de esa ocasión — más grande, ocasión más clara."
        )
    with m2:
        ac.fig_and_download(viz.pass_map(events, player, comp_label, display), "mapa_pases.png")
        st.caption(
            "**Mapa de pases**: en azul, pases **progresivos** (avanzan el balón hacia la "
            "portería rival); en naranja, pases **clave** (el que precede directamente a un tiro)."
        )

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
