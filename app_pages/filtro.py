"""Filtro avanzado: criba la competición cargada por posición y percentiles.

A diferencia del Buscador (encuentra a un jugador por nombre), esto es un
cribador — el mismo tipo de filtro que hace un scout con Wyscout/Driblab
antes de ponerse a ver vídeo de nadie: "quiero laterales con percentil 80+
en conducciones progresivas", no un jugador concreto.
"""

import streamlit as st

from futbol_analytics import narrative, viz

ctx = st.session_state["ctx"]
table = ctx["table"]
display_of = ctx["display_of"]

st.title("🎚️ Filtro avanzado")
st.caption(
    "Criba la competición cargada por posición y percentiles de rendimiento — "
    "los mismos percentiles que ves en la ficha de cada jugador, aquí aplicados "
    "de golpe a toda la competición. Respeta los minutos mínimos y el grupo/rol "
    "de comparación que hayas puesto arriba."
)

c_grupo, c_equipo = st.columns([1, 2])
grupos = ["Todos"] + sorted(table["position_group"].dropna().unique())
grupo = c_grupo.selectbox("Posición", grupos, key="filtro_grupo")
equipos = ["Todos"] + sorted(table["team"].unique())
equipo = c_equipo.selectbox("Equipo", equipos, key="filtro_equipo")

pool = table if grupo == "Todos" else table[table["position_group"] == grupo]
if equipo != "Todos":
    pool = pool[pool["team"] == equipo]

# con "Todos" se ofrece la unión de las métricas de cada grupo (sin repetir),
# igual orden de aparición que en viz.RADAR_METRICS — la misma fuente que usa
# el radar del jugador y el comparador, para no inventar una lista aparte
if grupo == "Todos":
    vistas: dict[str, str] = {}
    for lst in viz.RADAR_METRICS.values():
        for col_pct, label in lst:
            vistas.setdefault(col_pct, label)
    metricas_disponibles = list(vistas.items())
else:
    metricas_disponibles = viz.RADAR_METRICS.get(grupo, viz.RADAR_METRICS["MF"])

label_of = {col_pct: label.replace("\n", " ") for col_pct, label in metricas_disponibles}

seleccion = st.multiselect(
    "Métricas a exigir (percentil mínimo)",
    list(label_of),
    default=list(label_of)[:2],
    format_func=lambda c: label_of[c],
    key="filtro_metricas",
)

umbrales: dict[str, int] = {}
if seleccion:
    cols_sliders = st.columns(len(seleccion))
    for c, col_pct in zip(cols_sliders, seleccion):
        umbrales[col_pct] = c.slider(label_of[col_pct], 0, 100, 70, 5, key=f"filtro_umbral_{col_pct}")

resultado = pool.copy()
for col_pct, umbral in umbrales.items():
    resultado = resultado[resultado[col_pct] >= umbral]

if umbrales:
    resultado = resultado.assign(_media_pct=resultado[list(umbrales)].mean(axis=1))
    resultado = resultado.sort_values("_media_pct", ascending=False)

st.markdown(f"#### {len(resultado)} jugador(es) de {len(pool)} en el filtro")

if not umbrales:
    st.info("Elige al menos una métrica para empezar a cribar.")
elif resultado.empty:
    st.warning("Ningún jugador cumple todos los umbrales a la vez — baja alguno o quita una métrica.")
else:
    vista = resultado.copy()
    vista["player"] = vista["player"].map(display_of).fillna(vista["player"])
    cols_metricas = list(umbrales)

    lectura = narrative.shortlist_reading(vista, cols_metricas, label_of)
    if lectura:
        st.markdown(f"**Lectura:** {lectura}")

    rename = {
        "player": "Jugador",
        "team": "Equipo",
        "primary_position": "Posición",
        "minutes": "Minutos",
    }
    rename |= {c: f"p {label_of[c]}" for c in cols_metricas}
    tabla = vista[["player", "team", "primary_position", "minutes", *cols_metricas]].rename(columns=rename)

    column_config = {
        f"p {label_of[c]}": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")
        for c in cols_metricas
    }
    st.dataframe(tabla, use_container_width=True, hide_index=True, column_config=column_config)

    st.download_button(
        "⬇ CSV",
        resultado.drop(columns="_media_pct").to_csv(index=False).encode("utf-8"),
        file_name="filtro_jugadores.csv",
        mime="text/csv",
        key="csv_filtro",
    )

with st.expander("Cómo funciona el filtro"):
    st.markdown(
        """
Cada percentil compara al jugador contra su grupo posicional (o su rol fino, si
lo has elegido arriba) dentro de la competición cargada — el mismo
cálculo que alimenta el radar de cada ficha, aquí aplicado como corte en vez de
como gráfico. Con varias métricas a la vez, un jugador solo aparece si supera
**todos** los umbrales, y la tabla se ordena por la media de sus percentiles
seleccionados — no hay ningún modelo nuevo detrás, es el mismo dato que ya ves
en el resto de la app.
"""
    )
