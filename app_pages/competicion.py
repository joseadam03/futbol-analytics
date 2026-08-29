"""Vista de toda la competición: dispersión interactiva y tabla completa."""

import altair as alt
import streamlit as st

import app_common as ac
from futbol_analytics import metrics

ctx = st.session_state["ctx"]
table = ctx["table"]
player, display, display_of = ctx["player"], ctx["display"], ctx["display_of"]

st.title("Competición")
st.caption(f"{ctx['comp_label']} · {len(table)} jugadores con ≥{ctx['min_minutes']:.0f} minutos")

axis_options = {
    "npxG/90": "npxg_p90", "xA/90": "xa_p90", "Tiros/90": "shots_p90",
    "Pases clave/90": "key_passes_p90", "Pases progresivos/90": "prog_passes_p90",
    "Conducciones progresivas/90": "prog_carries_p90", "Regates/90": "dribbles_cmp_p90",
    "Toques en área/90": "touches_box_p90", "% pase": "pass_pct",
    "Presiones/90": "pressures_p90", "PAdj Entradas+Int/90": "padj_tack_int_p90",
    "Recuperaciones/90": "recoveries_p90",
}
cx, cy = st.columns(2)
x_label = cx.selectbox("Eje X", list(axis_options), index=0)
y_label = cy.selectbox("Eje Y", list(axis_options), index=1)

pool = table[table["position_group"].isin(["DF", "MF", "FW"])].copy()
pool["display"] = pool["player"].map(display_of)
base = alt.Chart(pool).mark_circle(size=90, opacity=0.75).encode(
    x=alt.X(axis_options[x_label], title=x_label),
    y=alt.Y(axis_options[y_label], title=y_label),
    color=alt.Color(
        "position_group",
        title="Posición",
        scale=alt.Scale(domain=["DF", "MF", "FW"], range=ac.SCATTER_COLORS[ctx["theme"]]),
    ),
    tooltip=[
        alt.Tooltip("display", title="Jugador"),
        alt.Tooltip("team", title="Equipo"),
        alt.Tooltip("minutes", title="Minutos", format=".0f"),
        alt.Tooltip(axis_options[x_label], title=x_label, format=".2f"),
        alt.Tooltip(axis_options[y_label], title=y_label, format=".2f"),
    ],
)
sel = pool[pool["player"] == player]
highlight = alt.Chart(sel).mark_point(
    size=320, shape="circle", filled=False, strokeWidth=3
).encode(
    x=alt.X(axis_options[x_label]),
    y=alt.Y(axis_options[y_label]),
    color=alt.value(ac.HIGHLIGHT[ctx["theme"]]),
    tooltip=[alt.Tooltip("display", title="Jugador")],
)
st.altair_chart(base + highlight, use_container_width=True)
st.caption(f"El anillo marca a {display}. Porteros excluidos. Pasa el ratón para ver cada jugador.")

st.markdown("#### Tabla completa")
show_cols = ["nickname", "team", "position_group", "minutes"] + [
    f"{m}_p90" for m in metrics.COUNT_METRICS
] + ["pass_pct", "npxg_per_shot"]
st.dataframe(
    table[show_cols].round(2).rename(columns={"nickname": "player"}),
    use_container_width=True, hide_index=True,
)
st.download_button(
    "Descargar CSV completo",
    table.to_csv(index=False).encode(),
    file_name=f"metricas_{ctx['comp']['competition_id']}_{ctx['comp']['season_id']}.csv",
    mime="text/csv",
)
