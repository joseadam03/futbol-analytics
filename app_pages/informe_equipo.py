"""Informe de equipo: cómo juega, no solo cuánto rinde."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import teams as tm
from futbol_analytics import viz

ctx = st.session_state["ctx"]

st.title("🛡️ Informe de equipo")
st.caption(
    "Estilo de juego en tres familias — ritmo, presión y progresión — medido en "
    f"percentiles dentro de {ctx['comp_label']}. Un percentil alto significa *más* "
    "de ese rasgo, no necesariamente mejor."
)

equipos = sorted(ctx["table"]["team"].unique())
propio = str(ctx["prow"]["team"])
equipo = st.selectbox(
    "Equipo",
    equipos,
    index=equipos.index(propio) if propio in equipos else 0,
    key="informe_team",
)

rendimiento = ac.team_table(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
estilo = ac.team_style_table(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
fila_r = rendimiento[rendimiento["team"] == equipo].iloc[0]
fila_e = estilo[estilo["team"] == equipo].iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Partidos", f"{fila_r['matches']:.0f}")
c2.metric("Posesión", f"{fila_r['possession']:.1f} %")
c3.metric("npxG dif./partido", f"{fila_r['npxg_diff_pm']:+.2f}")
c4.metric("PPDA", f"{fila_r['ppda']:.1f}" if pd.notna(fila_r["ppda"]) else "—")
c5.metric("Field tilt", f"{fila_e['field_tilt']:.1f} %" if pd.notna(fila_e["field_tilt"]) else "—")

izq, der = st.columns([3, 2])
with izq:
    ac.fig_and_download(viz.team_radar(fila_e, ctx["comp_label"], equipo), "radar_equipo.png")
with der:
    st.markdown("#### Perfil de estilo")
    filas = []
    for col, etiqueta in tm.STYLE_METRICS.items():
        if col not in estilo.columns or pd.isna(fila_e[col]):
            continue
        filas.append(
            {
                "Métrica": etiqueta,
                "Valor": round(float(fila_e[col]), 2),
                "Percentil": round(float(fila_e.get(f"{col}_pct", float("nan")))),
            }
        )
    st.dataframe(
        pd.DataFrame(filas),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Percentil": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")
        },
    )
    st.caption(
        "El percentil del **PPDA** va invertido: alto = presiona más. El resto se lee "
        "en su dirección natural."
    )

st.markdown("#### Lectura del estilo")
lineas = []
if pd.notna(fila_e.get("passes_per_possession_pct")):
    lineas.append(
        f"- **Ritmo**: {fila_e['passes_per_possession']:.1f} pases por posesión "
        f"(percentil {fila_e['passes_per_possession_pct']:.0f}) con pases de "
        f"{fila_e['pass_length']:.1f} unidades de media y un "
        f"{fila_e['long_pass_share']:.1f} % de pases largos."
    )
if pd.notna(fila_e.get("recovery_height_pct")):
    lineas.append(
        f"- **Presión**: recupera a {fila_e['recovery_height']:.1f} de media en el eje largo "
        f"(percentil {fila_e['recovery_height_pct']:.0f}), con "
        f"{fila_e['pressures_pm']:.0f} presiones por partido."
    )
if pd.notna(fila_e.get("prog_pass_share_pct")):
    lineas.append(
        f"- **Progresión**: un {fila_e['prog_pass_share']:.1f} % de sus pases en juego son "
        f"progresivos (percentil {fila_e['prog_pass_share_pct']:.0f}) y entra "
        f"{fila_e['final_third_pm']:.1f} veces por partido al último tercio."
    )
st.markdown("\n".join(lineas) if lineas else "_Sin datos suficientes para el perfil de estilo._")

st.markdown("#### Toda la competición")
tabla = estilo.copy()
cols = ["team"] + [c for c in tm.STYLE_METRICS if c in tabla.columns]
st.dataframe(
    tabla[cols].round(2).rename(columns={"team": "Equipo", **tm.STYLE_METRICS}),
    use_container_width=True,
    hide_index=True,
)
st.download_button(
    "⬇ CSV",
    estilo.to_csv(index=False).encode("utf-8"),
    file_name="estilo_equipos.csv",
    mime="text/csv",
    key="csv_estilo",
)

with st.expander("Cómo se miden estos rasgos"):
    st.markdown(
        """
- **Ritmo** — longitud media de pase, cuota de pases largos (≥ 30 unidades, ~27 m) y
  **pases por posesión**: cuántos pases encadena el equipo en cada secuencia. Más
  pases por posesión = juego más elaborado; menos = más directo.
- **Presión** — **PPDA** (pases que se permiten al rival en su construcción por cada
  acción defensiva propia en campo contrario; más bajo = más intenso), presiones por
  partido y **altura de recuperación**: la x media de sus acciones defensivas.
- **Progresión** — cuota de pases progresivos, conducciones progresivas por partido,
  **entradas al último tercio** (pases y conducciones que cruzan x = 80) y **field
  tilt**: qué porcentaje de los toques en el último tercio de cada partido son suyos,
  una medida de dominio territorial que no depende del volumen de posesión.
- Todo excluye las tandas de penaltis, como el resto del proyecto. En torneos cortos,
  estos rasgos se estiman con muy pocos partidos: léelos como tendencia, no como ley.
"""
    )
