"""Fútbol Analytics — app de análisis de jugadores.

Ejecutar:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from futbol_analytics import metrics, photos, similarity, viz
from futbol_analytics.providers import get_provider, list_providers

st.set_page_config(page_title="Fútbol Analytics", page_icon="⚽", layout="wide")

# Tema: los gráficos matplotlib siguen el tema claro/oscuro del usuario.
THEME = getattr(getattr(st.context, "theme", None), "type", None) or "light"
viz.use_theme(THEME)

SCATTER_COLORS = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
    "dark": ["#3987e5", "#d95926", "#199e70"],
}[THEME]


@st.cache_data(show_spinner=False)
def load_competitions(provider_key: str) -> pd.DataFrame:
    comps = get_provider(provider_key).competitions()
    comps = comps.drop_duplicates(subset=["competition_id", "season_id"])
    comps["label"] = comps["competition_name"] + " · " + comps["season_name"]
    return comps


@st.cache_data(show_spinner=False)
def load_events(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    return get_provider(provider_key).events(competition_id, season_id)


@st.cache_data(show_spinner=False)
def load_minutes(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    provider = get_provider(provider_key)
    events = provider.events(competition_id, season_id)
    return provider.minutes_played(competition_id, season_id, events)


@st.cache_data(show_spinner=False)
def build_table(
    provider_key: str, competition_id: int, season_id: int, min_minutes: float
) -> pd.DataFrame:
    events = load_events(provider_key, competition_id, season_id)
    minutes = load_minutes(provider_key, competition_id, season_id)
    table = metrics.player_metrics(events, minutes, min_minutes=min_minutes)
    pct_cols = [f"{m}_p90" for m in metrics.COUNT_METRICS] + ["pass_pct", "npxg_per_shot"]
    return metrics.percentiles(table, pct_cols)


@st.cache_data(show_spinner=False)
def photo_of(display_name: str) -> str | None:
    return photos.photo_url(display_name)


# ---------------------------------------------------------------- barra lateral
st.sidebar.title("⚽ Fútbol Analytics")

providers = list_providers()
provider_key = st.sidebar.selectbox(
    "Proveedor de datos",
    options=list(providers),
    format_func=lambda k: providers[k].name,
)
if not providers[provider_key].available():
    st.sidebar.warning("Este proveedor aún no está disponible.")
    st.info(
        "**Wyscout está preparado pero pendiente de credenciales.** "
        "La arquitectura de proveedores ya soporta añadirlo: implementar el mapeo "
        "de eventos en `src/futbol_analytics/providers/wyscout.py` y definir "
        "`WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET`. "
        "Mientras tanto, usa StatsBomb (open data)."
    )
    st.stop()

comps = load_competitions(provider_key)
labels = comps["label"].tolist()
default_ix = labels.index("FIFA World Cup · 2022") if "FIFA World Cup · 2022" in labels else 0
comp_label = st.sidebar.selectbox("Competición", labels, index=default_ix)
comp = comps[comps["label"] == comp_label].iloc[0]

min_minutes = st.sidebar.slider("Minutos mínimos (percentiles)", 0, 900, 180, 30)

with st.spinner("Cargando datos... (la primera descarga de una competición tarda varios minutos)"):
    table = build_table(provider_key, int(comp["competition_id"]), int(comp["season_id"]), min_minutes)
    events = load_events(provider_key, int(comp["competition_id"]), int(comp["season_id"]))

if "nickname" not in table.columns:
    table["nickname"] = table["player"]
display_of = dict(zip(table["player"], table["nickname"].fillna(table["player"])))

player = st.sidebar.selectbox(
    "Jugador", sorted(table["player"], key=lambda p: display_of[p]), format_func=display_of.get
)
prow = table[table["player"] == player].iloc[0]
display = display_of[player]

st.sidebar.caption(
    f"{len(table)} jugadores con ≥{min_minutes:.0f} min · "
    "Datos: StatsBomb open data (uso no comercial)"
)

# ------------------------------------------------------------------- cabecera
photo_col, info_col = st.columns([1, 6])
with photo_col:
    url = photo_of(display)
    if url:
        st.image(url, width=110)
with info_col:
    st.title(display)
    st.caption(
        f"{prow['team']} · {prow['primary_position']} ({prow['position_group']}) · "
        f"{prow['minutes']:.0f} minutos · {comp_label}"
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

sims = similarity.similar_players(table, player)

# ---------------------------------------------------------------------- tabs
tab_radar, tab_mapas, tab_comparar, tab_similares, tab_comp, tab_metodo = st.tabs(
    ["Radar", "Mapas", "Comparar", "Similares", "Competición", "Metodología"]
)

with tab_radar:
    left, right = st.columns([3, 2])
    with left:
        st.pyplot(viz.radar_chart(prow, comp_label, display), use_container_width=True)
    with right:
        st.markdown("#### Lectura")
        group = prow["position_group"]
        st.markdown(
            f"Cada eje es el **percentil per-90 del jugador frente a los {group} "
            f"de la competición** con al menos {min_minutes:.0f} minutos. "
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
        st.pyplot(viz.touch_heatmap(events, player, comp_label, display), use_container_width=True)
        st.pyplot(viz.shot_map(events, player, comp_label, display), use_container_width=True)
    with m2:
        st.pyplot(viz.pass_map(events, player, comp_label, display), use_container_width=True)

with tab_comparar:
    same_group = table[
        (table["position_group"] == prow["position_group"]) & (table["player"] != player)
    ]
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
        st.pyplot(
            viz.radar_compare(prow, rrow, comp_label, display, display_of[rival]),
            use_container_width=True,
        )
    with right:
        rp = photo_of(display_of[rival])
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

with tab_similares:
    st.markdown(
        "Perfiles más parecidos por **similitud de coseno** sobre métricas per-90 "
        "estandarizadas dentro del grupo posicional: compara *a qué se dedica* el "
        "jugador, no su volumen bruto."
    )
    sims_view = sims.copy()
    sims_view.insert(0, "Foto", [photo_of(display_of.get(p, p)) or "" for p in sims_view["player"]])
    sims_view["player"] = sims_view["player"].map(display_of)
    st.dataframe(
        sims_view.rename(
            columns={
                "player": "Jugador", "team": "Equipo", "primary_position": "Posición",
                "minutes": "Minutos", "similarity": "Similitud",
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

with tab_comp:
    st.markdown("#### Toda la competición de un vistazo")
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
            scale=alt.Scale(domain=["DF", "MF", "FW"], range=SCATTER_COLORS),
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
        color=alt.value("#e34948" if THEME == "light" else "#e66767"),
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
        file_name=f"metricas_{comp['competition_id']}_{comp['season_id']}.csv",
        mime="text/csv",
    )

with tab_metodo:
    st.markdown(
        """
#### Cómo se calcula cada métrica

| Métrica | Definición |
|---|---|
| **Minutos** | Derivados de alineaciones oficiales (titularidad, cambios), no estimados |
| **npxG** | xG acumulado sin penaltis; tandas de penaltis excluidas de todo |
| **xA** | Cada pase clave hereda el xG del tiro que generó (`shot_key_pass_id`) |
| **Pase/conducción progresiva** | Reduce la distancia a portería rival ≥ 25 %; sin balón parado |
| **PAdj Entradas+Int.** | `(entradas + intercepciones) × 0.5 / (1 − posesión del equipo)` |
| **Toques en área** | Eventos con balón dentro del área rival |
| **Percentiles** | Rango dentro del grupo posicional (GK/DF/MF/FW) |
| **Similitud** | Coseno entre perfiles per-90 estandarizados (z-score) del grupo |

**Limitaciones**: percentiles válidos *dentro de la competición*; en torneos
cortos las métricas per-90 tienen alta varianza; la posesión se estima por
cuota de pases. Las fotos provienen de TheSportsDB y pueden faltar para
algunos jugadores. Detalle completo en el README del repositorio.
"""
    )
