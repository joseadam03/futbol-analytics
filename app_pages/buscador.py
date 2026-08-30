"""Buscador: localiza a un jugador, esté o no en los open data cargados.

Primero busca en la competición cargada (ahí hay informe completo de
eventos); si el jugador no está, recupera una ficha informativa de
TheSportsDB y ofrece enlaces para seguir el scouting fuera.
"""

import unicodedata
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import sportmonks, tsdb

ctx = st.session_state["ctx"]
table = ctx["table"]

st.title("🔍 Buscador de jugadores")
st.caption(
    "Si el jugador está en la competición cargada, salta directo a su informe "
    "completo. Si no está en los open data, tendrás su ficha informativa y "
    "enlaces de scouting: los open data de StatsBomb solo cubren competiciones "
    "concretas, no todo el fútbol profesional."
)

query = st.text_input(
    "Nombre del jugador",
    placeholder="p. ej. Aitana, Franculino Djú, Leo Saca...",
    key="buscador_query",
)
q = query.strip()
if not q:
    st.stop()
if len(q) < 3:
    st.info("Escribe al menos 3 letras.")
    st.stop()


def _norm(text: str) -> str:
    """minúsculas y sin tildes, para que 'Dju' encuentre a 'Djú'."""
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()


qn = _norm(q)
mask = table["player"].map(_norm).str.contains(qn, regex=False) | table["nickname"].map(_norm).str.contains(
    qn, regex=False
)
hits = table[mask]

if not hits.empty:
    st.success(f"**{len(hits)}** resultado(s) en {ctx['comp_label']}, con informe completo de eventos:")
    for _, row in hits.head(8).iterrows():
        c_info, c_btn = st.columns([4, 1])
        c_info.markdown(
            f"**{row['nickname']}** — {row['team']} · {row['primary_position']} · {row['minutes']:.0f} min"
        )
        if c_btn.button("Abrir informe", key=f"abrir_{row['player']}"):
            st.session_state["jump_to_player"] = row["player"]
            st.switch_page("app_pages/jugador.py")
else:
    st.warning(
        f"**«{q}» no está en {ctx['comp_label']}** (o no llega al umbral de minutos de la "
        "barra lateral). Buscamos su ficha fuera de los datos de eventos:"
    )
    with st.spinner("Consultando TheSportsDB..."):
        try:
            fichas = ac.buscar_fichas(q)
            servicio_caido = False
        except tsdb.ServiceUnavailable:
            fichas, servicio_caido = [], True

    if servicio_caido:
        st.error(
            "TheSportsDB no responde ahora mismo (caída, rate limit o bloqueo de "
            "Cloudflare). La app sigue funcionando: reintenta en unos minutos o usa "
            "los enlaces de scouting de abajo."
        )
    elif not fichas:
        st.info(
            f"TheSportsDB tampoco tiene ficha para «{q}». Prueba con el nombre "
            "completo, con otra grafía o con los enlaces de abajo."
        )

    for ficha in fichas[:5]:
        with st.container(border=True):
            c_foto, c_info = st.columns([1, 5])
            with c_foto:
                if ficha["foto"]:
                    st.image(ficha["foto"], width=110)
            with c_info:
                st.markdown(f"#### {ficha['nombre']}")
                linea = " · ".join(
                    str(v)
                    for v in (
                        ficha["equipo"],
                        ficha["posicion"],
                        ficha["nacionalidad"],
                        ficha["nacimiento"],
                    )
                    if v
                )
                st.markdown(linea if linea else "_Sin datos básicos._")
                detalles = " · ".join(
                    str(v) for v in (ficha["lugar_nacimiento"], ficha["altura"], ficha["estado"]) if v
                )
                if detalles:
                    st.caption(detalles)
            if ficha["descripcion"]:
                with st.expander("Biografía (TheSportsDB, en inglés)"):
                    texto = ficha["descripcion"]
                    st.write(texto[:1500] + ("…" if len(texto) > 1500 else ""))

    if fichas:
        st.caption(
            "Ficha informativa de TheSportsDB (API gratuita, uso no comercial). Sin datos "
            "de eventos no hay radar ni percentiles: para métricas de jugadores fuera de "
            "los open data hace falta un proveedor con cobertura (p. ej. Wyscout, cuya "
            "integración ya está preparada en la app)."
        )

    if sportmonks.available():
        st.markdown("#### Estadísticas de temporada (Sportmonks)")
        st.caption(
            "Sportmonks no da coordenadas de jugada (ese endpoint es un timeline de "
            "goles, tarjetas y cambios, no cada toque de balón), así que no alimenta el "
            "radar ni el mapa de calor — pero sí trae goles, asistencias, minutos y "
            "apariciones reales por temporada, verificados contra la API."
        )
        with st.spinner("Consultando Sportmonks..."):
            try:
                ficha_sm = ac.buscar_estadisticas_sportmonks(q)
                sm_caido = False
            except sportmonks.ServiceUnavailable:
                ficha_sm, sm_caido = None, True

        if sm_caido:
            st.error("Sportmonks no responde ahora mismo. Reintenta en unos minutos.")
        elif not ficha_sm:
            st.info(f"Sportmonks no tiene ficha para «{q}».")
        else:
            temporadas = ficha_sm.get("temporadas") or []
            if not temporadas:
                st.info(f"{ficha_sm['nombre']} está en Sportmonks pero sin estadísticas registradas.")
            else:
                tabla_sm = pd.DataFrame(temporadas).sort_values("season_name", ascending=False)
                cols = ["season_name"] + [c for c in sportmonks.STAT_LABELS if c in tabla_sm.columns]
                st.dataframe(
                    tabla_sm[cols].rename(columns={"season_name": "Temporada", **sportmonks.STAT_LABELS}),
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.caption(
            "💡 Con un token de Sportmonks (`SPORTMONKS_API_TOKEN` en `.env`) esta ficha "
            "incluiría también goles, asistencias y minutos reales por temporada."
        )

st.divider()
st.markdown("#### Seguir el scouting fuera de la app")
u = quote_plus(q)
st.markdown(
    f"[Transfermarkt](https://www.transfermarkt.es/schnellsuche/ergebnis/schnellsuche?query={u}) · "
    f"[Sofascore](https://www.sofascore.com/search?q={u}) · "
    f"[FBref](https://fbref.com/es/search/search.fcgi?search={u})"
)
