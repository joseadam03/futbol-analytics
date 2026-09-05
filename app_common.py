"""Estado y utilidades compartidas por todas las páginas de la app."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from futbol_analytics import (
    auth,
    crests,
    metrics,
    photos,
    report,
    sequences,
    series,
    sportmonks,
    teams,
    tsdb,
    viz,
    xg,
)
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
    provider_key: str,
    competition_id: int,
    season_id: int,
    min_minutes: float,
    basis: str = "position_group",
) -> pd.DataFrame:
    events = load_events(provider_key, competition_id, season_id)
    minutes = load_minutes(provider_key, competition_id, season_id)
    table = metrics.player_metrics(events, minutes, min_minutes=min_minutes)
    pct_cols = [f"{m}_p90" for m in metrics.COUNT_METRICS] + ["pass_pct", "npxg_per_shot"]
    return metrics.percentiles(table, pct_cols, group_col=basis)


def pool_label(prow: pd.Series) -> str:
    """Contra quién se comparó a este jugador: su rol fino o su grupo posicional."""
    if prow.get("pct_basis") == "role" and isinstance(prow.get("role"), str):
        return str(prow["role"]).lower() + "s"
    return str(prow["position_group"])


@st.cache_data(show_spinner=False)
def photo_of(display_name: str) -> str | None:
    return photos.photo_url(display_name)


@st.cache_data(show_spinner=False)
def crest_of(team: str) -> str | None:
    return crests.crest_url(team)


@st.cache_data(show_spinner=False, ttl=3600)
def buscar_fichas(query: str) -> list[dict]:
    """Fichas externas de TheSportsDB; propaga ServiceUnavailable (no se cachea)."""
    return tsdb.search_players(query)


@st.cache_data(show_spinner=False, ttl=3600)
def buscar_estadisticas_sportmonks(query: str) -> dict | None:
    """Ficha con estadísticas de temporada (Sportmonks); propaga ServiceUnavailable."""
    return sportmonks.player_ficha(query)


@st.cache_data(show_spinner=False)
def team_table(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    """Rendimiento por equipo: posesión, npxG a favor/en contra, PPDA."""
    return teams.team_metrics(load_events(provider_key, competition_id, season_id))


@st.cache_data(show_spinner=False)
def team_style_table(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    """Estilo por equipo (ritmo, presión, progresión) con sus percentiles."""
    events = load_events(provider_key, competition_id, season_id)
    return teams.team_style_percentiles(teams.team_style_metrics(events))


@st.cache_data(show_spinner=False)
def load_matches(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    """Calendario de la competición (fechas y jornadas) para ordenar las series."""
    try:
        return get_provider(provider_key).matches(competition_id, season_id)
    except Exception:  # un proveedor sin calendario no debe tumbar la página
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def sequence_table(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    """Posesiones que acaban en tiro, con su origen y su forma."""
    events = load_events(provider_key, competition_id, season_id)
    return sequences.shot_sequences(events)


@st.cache_data(show_spinner=False)
def team_series_table(provider_key: str, competition_id: int, season_id: int) -> pd.DataFrame:
    """Métricas por equipo y partido, en orden temporal."""
    events = load_events(provider_key, competition_id, season_id)
    return series.team_series(events, load_matches(provider_key, competition_id, season_id))


@st.cache_data(show_spinner=False)
def player_series_table(provider_key: str, competition_id: int, season_id: int, player: str) -> pd.DataFrame:
    """Producción de un jugador partido a partido."""
    events = load_events(provider_key, competition_id, season_id)
    return series.player_series(events, player, load_matches(provider_key, competition_id, season_id))


@st.cache_data(show_spinner=False)
def entrena_xg(provider_key: str, competition_id: int, season_id: int):
    """Entrena el modelo de xG propio sobre la competición (resumen, tiros)."""
    events = load_events(provider_key, competition_id, season_id)
    return xg.train_xg(events)


@st.cache_data(show_spinner=False)
def informe_pdf(
    provider_key: str,
    competition_id: int,
    season_id: int,
    min_minutes: float,
    player: str,
    comp_label: str,
    basis: str = "position_group",
) -> bytes:
    """Informe-CV en PDF del jugador (siempre en tema claro, para imprimir)."""
    table = build_table(provider_key, competition_id, season_id, min_minutes, basis)
    events = load_events(provider_key, competition_id, season_id)
    prow = table[table["player"] == player].iloc[0]
    apodo = prow.get("nickname")
    display = apodo if isinstance(apodo, str) and apodo else player
    try:
        return report.player_report_pdf(
            table,
            events,
            player,
            comp_label,
            photo_url=photo_of(display),
            crest_url=crest_of(str(prow["team"])),
        )
    finally:
        viz.use_theme(theme())  # el informe fuerza tema claro; restaurar el de la app


@st.cache_data(show_spinner=False)
def ficha_informe_pdf(ficha: dict | None, ficha_sm: dict | None, query: str) -> bytes:
    """Informe-CV ligero (bio + estadísticas de temporada) para un jugador fuera de los open data."""
    equipo = (ficha or {}).get("equipo")
    try:
        return report.ficha_report_pdf(ficha, ficha_sm, query, crest_url=crest_of(equipo) if equipo else None)
    finally:
        viz.use_theme(theme())  # el informe fuerza tema claro; restaurar el de la app


def cached_competitions(provider_key: str) -> pd.DataFrame:
    """Competiciones cuyos eventos ya están en la caché local (carga instantánea)."""
    comps = load_competitions(provider_key)
    provider = get_provider(provider_key)
    mask = [provider.has_cached(int(row.competition_id), int(row.season_id)) for row in comps.itertuples()]
    return comps[pd.Series(mask, index=comps.index)]


def _stop_with_data_error(exc: Exception) -> None:
    """Aviso amable en lugar del traceback cuando falla la descarga de datos."""
    st.error(
        "**No se pudieron cargar los datos.** Suele ser un problema transitorio "
        "de red o del proveedor (los open data de StatsBomb se descargan de GitHub; "
        "las fotos, de TheSportsDB). Comprueba la conexión y reintenta."
    )
    with st.expander("Detalle técnico"):
        st.code(f"{type(exc).__name__}: {exc}")
    if st.button("Reintentar", key="retry_data"):
        st.cache_data.clear()
        st.rerun()
    st.stop()


def sidebar_context() -> dict:
    """Dibuja la barra lateral global y devuelve la selección actual."""
    viz.use_theme(theme())

    usuario = auth.usuario_actual()
    forzado = usuario.get("provider") if usuario else None
    providers = list_providers(include_fake=True if forzado == "fake" else None)
    keys = list(providers)
    provider_key = st.sidebar.selectbox(
        "Proveedor de datos",
        options=keys,
        index=keys.index(forzado) if forzado in keys else 0,
        format_func=lambda k: providers[k].name,
        key="provider_sel",
    )
    if not providers[provider_key].available():
        st.sidebar.warning("Este proveedor aún no está disponible.")
        st.info(
            "**Wyscout está implementado pero pendiente de credenciales.** El mapeo de "
            "eventos, los minutos y el calendario están escritos y cubiertos por tests; "
            "solo faltan `WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET` en tu `.env`. "
            "Mientras tanto, usa StatsBomb (open data)."
        )
        st.stop()

    try:
        comps = load_competitions(provider_key)
    except Exception as exc:  # red o proveedor caídos
        _stop_with_data_error(exc)
    labels = comps["label"].tolist()
    default_ix = labels.index("FIFA World Cup · 2022") if "FIFA World Cup · 2022" in labels else 0
    comp_label = st.sidebar.selectbox("Competición", labels, index=default_ix, key="comp_sel")
    comp = comps[comps["label"] == comp_label].iloc[0]

    min_minutes = st.sidebar.slider("Minutos mínimos (percentiles)", 0, 900, 180, 30, key="min_sel")
    basis = st.sidebar.radio(
        "Comparar contra",
        ["position_group", "role"],
        format_func=lambda b: "Grupo posicional" if b == "position_group" else "Rol (lateral ≠ central)",
        key="basis_sel",
        help=(
            "El rol fino compara peras con peras, pero adelgaza la muestra: los roles con "
            f"menos de {metrics.MIN_ROLE_SIZE} jugadores caen automáticamente a su grupo posicional."
        ),
    )

    with st.spinner("Cargando datos... (la primera descarga de una competición tarda varios minutos)"):
        try:
            table = build_table(
                provider_key, int(comp["competition_id"]), int(comp["season_id"]), min_minutes, basis
            )
            events = load_events(provider_key, int(comp["competition_id"]), int(comp["season_id"]))
        except Exception as exc:  # red o proveedor caídos a mitad de descarga
            _stop_with_data_error(exc)

    if table.empty:
        st.warning(
            f"Ningún jugador alcanza {min_minutes:.0f} minutos en esta competición. "
            "Baja el umbral de minutos en la barra lateral."
        )
        st.stop()

    if "nickname" not in table.columns:
        table["nickname"] = table["player"]
    table["nickname"] = table["nickname"].fillna(table["player"])
    display_of = dict(zip(table["player"], table["nickname"]))

    # salto desde el Buscador: fijar la selección antes de instanciar el widget
    jump = st.session_state.pop("jump_to_player", None)
    if jump is not None and jump in set(table["player"]):
        st.session_state["player_sel"] = jump

    player = st.sidebar.selectbox(
        "Jugador",
        sorted(table["player"], key=lambda p: display_of[p]),
        format_func=lambda p: display_of.get(p, p),
        key="player_sel",
    )
    st.sidebar.caption(
        f"{len(table)} jugadores con ≥{min_minutes:.0f} min · Datos: StatsBomb open data (uso no comercial)"
    )

    prow = table[table["player"] == player].iloc[0]
    return {
        "provider_key": provider_key,
        "comp": comp,
        "comp_label": comp_label,
        "min_minutes": min_minutes,
        "basis": basis,
        "pool_label": pool_label(prow),
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
    st.download_button("⬇ PNG", buf.getvalue(), file_name=filename, mime="image/png", key=f"dl_{filename}")
