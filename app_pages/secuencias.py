"""Secuencias de posesión: de dónde nacen las ocasiones de cada equipo."""

import altair as alt
import streamlit as st

import app_common as ac
from futbol_analytics import sequences as sq

ctx = st.session_state["ctx"]

st.title("🧵 Secuencias de posesión")
st.caption(
    "¿Este equipo crea desde el juego elaborado, del balón parado o robando arriba? "
    "Cada posesión que acaba en tiro se clasifica por su origen y su forma."
)

seqs = ac.sequence_table(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
if seqs.empty:
    st.info(
        "Estos datos no traen secuencias de posesión (falta la columna `possession`), "
        "así que no se puede reconstruir el origen de las ocasiones."
    )
    st.stop()

perfil = sq.team_sequence_profile(seqs)
equipos = sorted(perfil["team"])
propio = str(ctx["prow"]["team"])
equipo = st.selectbox(
    "Equipo", equipos, index=equipos.index(propio) if propio in equipos else 0, key="seq_team"
)
fila = perfil[perfil["team"] == equipo].iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Ocasiones", f"{fila['sequences']:.0f}")
c2.metric("npxG total", f"{fila['npxg']:.2f}")
c3.metric("Pases antes de tirar", f"{fila['passes_before']:.1f}")
c4.metric("Duración media", f"{fila['duration']:.0f} s")
c5.metric("Nacen en campo rival", f"{fila['high_start_share']:.0f} %")

izq, der = st.columns([3, 2])
with izq:
    st.markdown(f"#### De dónde nace el peligro de **{equipo}**")
    desglose = sq.pattern_breakdown(seqs, equipo)
    color = ac.SCATTER_COLORS[ctx["theme"]][0]
    grafico = (
        alt.Chart(desglose)
        .mark_bar(color=color, opacity=0.85)
        .encode(
            x=alt.X("npxg", title="npxG generado"),
            y=alt.Y("label", title=None, sort="-x"),
            tooltip=[
                alt.Tooltip("label", title="Origen"),
                alt.Tooltip("sequences", title="Ocasiones"),
                alt.Tooltip("npxg", title="npxG", format=".2f"),
                alt.Tooltip("goals", title="Goles", format=".0f"),
                alt.Tooltip("npxg_share", title="% del npxG", format=".1f"),
            ],
        )
    )
    st.altair_chart(grafico, use_container_width=True)
with der:
    st.markdown("#### Reparto")
    st.dataframe(
        desglose[["label", "sequences", "npxg", "goals", "npxg_share"]].rename(
            columns={
                "label": "Origen",
                "sequences": "Ocasiones",
                "npxg": "npxG",
                "goals": "Goles",
                "npxg_share": "% npxG",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "npxG": st.column_config.NumberColumn(format="%.2f"),
            "Goles": st.column_config.NumberColumn(format="%.0f"),
            "% npxG": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
        },
    )

st.markdown("#### Elaboración frente a verticalidad")
st.caption(
    "A la derecha, equipos que encadenan muchos pases antes de tirar; arriba, los que "
    "avanzan más rápido hacia la portería. El tamaño es el npxG generado."
)
base = alt.Chart(perfil).encode(
    x=alt.X("passes_before", title="Pases antes de tirar", scale=alt.Scale(zero=False)),
    y=alt.Y("direct_speed", title="Velocidad directa (unidades/s)", scale=alt.Scale(zero=False)),
    tooltip=[
        alt.Tooltip("team", title="Equipo"),
        alt.Tooltip("npxg", title="npxG", format=".2f"),
        alt.Tooltip("passes_before", title="Pases previos", format=".1f"),
        alt.Tooltip("direct_speed", title="Velocidad directa", format=".2f"),
        alt.Tooltip("set_piece_share", title="% balón parado", format=".0f"),
    ],
)
ink = "#0b0b0b" if ctx["theme"] == "light" else "#ffffff"
puntos = base.mark_circle(opacity=0.8, color=ac.SCATTER_COLORS[ctx["theme"]][0]).encode(
    size=alt.Size("npxg", legend=None, scale=alt.Scale(range=[60, 500]))
)
etiquetas = base.mark_text(align="left", dx=10, fontSize=10, color=ink).encode(text="team")
st.altair_chart(puntos + etiquetas, use_container_width=True)

st.markdown("#### Perfil de todos los equipos")
cols = {
    "team": "Equipo",
    "sequences": "Ocasiones",
    "npxg": "npxG",
    "npxg_per_sequence": "npxG/ocasión",
    "passes_before": "Pases previos",
    "duration": "Duración (s)",
    "direct_speed": "Velocidad directa",
    "high_start_share": "% nacen arriba",
    "build_up_share": "% juego regular",
    "set_piece_share": "% balón parado",
    "direct_share": "% transición",
}
st.dataframe(perfil[list(cols)].round(2).rename(columns=cols), use_container_width=True, hide_index=True)
st.download_button(
    "⬇ CSV",
    perfil.to_csv(index=False).encode("utf-8"),
    file_name="secuencias_equipos.csv",
    mime="text/csv",
    key="csv_seq",
)

with st.expander("Cómo se mide una secuencia"):
    st.markdown(
        """
- Una **posesión** es una secuencia continua de acciones de un equipo; StatsBomb las
  numera y etiqueta cómo empezaron (juego regular, córner, falta, saque de banda,
  contragolpe, saque de puerta...). Solo se analizan las que acaban en tiro.
- **Zona de inicio**: la x del primer evento del equipo en la posesión. Arrancar en
  campo contrario (x ≥ 60) se cuenta como *nacida arriba*: un robo, no una construcción.
- **Pases previos**: pases propios antes del primer tiro de la secuencia. Muchos =
  elaboración; cero o uno = transición.
- **Velocidad directa**: cuánto avanza el balón hacia la portería rival por segundo.
  Ojo: las secuencias de balón parado empiezan ya cerca del área, así que su
  progresión —y su velocidad— sale baja por construcción, no por lentitud.
- Penaltis y tandas excluidos, como en el resto del proyecto.
"""
    )
