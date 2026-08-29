"""Estado y utilidades compartidas por todas las páginas de la app."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from futbol_analytics import metrics, photos, viz
from futbol_analytics.providers import get_provider, list_providers

SCATTER_COLORS = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
    "dark": ["#3987e5", "#d95926", "#199e70"],
}
HIGHLIGHT = {"light": "#e34948", "dark": "#e66767"}


def theme() -> str:
    return getattr(getattr(st.context, "theme", None), "type", None) or "light"


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


def sidebar_context() -> dict:
    """Dibuja la barra lateral global y devuelve la selección actual."""
    viz.use_theme(theme())

    providers = list_providers()
    provider_key = st.sidebar.selectbox(
        "Proveedor de datos",
        options=list(providers),
        format_func=lambda k: providers[k].name,
        key="provider_sel",
    )
    if not providers[provider_key].available():
        st.sidebar.warning("Este proveedor aún no está disponible.")
        st.info(
            "**Wyscout está preparado pero pendiente de credenciales.** "
            "Implementar el mapeo de eventos en `providers/wyscout.py` y definir "
            "`WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET`. "
            "Mientras tanto, usa StatsBomb (open data)."
        )
        st.stop()

    comps = load_competitions(provider_key)
    labels = comps["label"].tolist()
    default_ix = labels.index("FIFA World Cup · 2022") if "FIFA World Cup · 2022" in labels else 0
    comp_label = st.sidebar.selectbox("Competición", labels, index=default_ix, key="comp_sel")
    comp = comps[comps["label"] == comp_label].iloc[0]

    min_minutes = st.sidebar.slider("Minutos mínimos (percentiles)", 0, 900, 180, 30, key="min_sel")

    with st.spinner("Cargando datos... (la primera descarga de una competición tarda varios minutos)"):
        table = build_table(
            provider_key, int(comp["competition_id"]), int(comp["season_id"]), min_minutes
        )
        events = load_events(provider_key, int(comp["competition_id"]), int(comp["season_id"]))

    if "nickname" not in table.columns:
        table["nickname"] = table["player"]
    table["nickname"] = table["nickname"].fillna(table["player"])
    display_of = dict(zip(table["player"], table["nickname"]))

    player = st.sidebar.selectbox(
        "Jugador",
        sorted(table["player"], key=lambda p: display_of[p]),
        format_func=display_of.get,
        key="player_sel",
    )
    st.sidebar.caption(
        f"{len(table)} jugadores con ≥{min_minutes:.0f} min · "
        "Datos: StatsBomb open data (uso no comercial)"
    )

    prow = table[table["player"] == player].iloc[0]
    return {
        "provider_key": provider_key,
        "comp": comp,
        "comp_label": comp_label,
        "min_minutes": min_minutes,
        "table": table,
        "events": events,
        "player": player,
        "prow": prow,
        "display": display_of[player],
        "display_of": display_of,
        "theme": theme(),
    }


def player_header(ctx: dict) -> None:
    prow = ctx["prow"]
    photo_col, info_col = st.columns([1, 6])
    with photo_col:
        url = photo_of(ctx["display"])
        if url:
            st.image(url, width=110)
    with info_col:
        st.title(ctx["display"])
        st.caption(
            f"{prow['team']} · {prow['primary_position']} ({prow['position_group']}) · "
            f"{prow['minutes']:.0f} minutos · {ctx['comp_label']}"
        )


def fig_and_download(fig, filename: str) -> None:
    """Muestra una figura matplotlib con botón de descarga en PNG."""
    st.pyplot(fig, use_container_width=True)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=fig.get_facecolor(), bbox_inches="tight")
    st.download_button(
        "⬇ PNG", buf.getvalue(), file_name=filename, mime="image/png", key=f"dl_{filename}"
    )
