"""Modelo de xG propio: un modelo transparente contrastado con el del proveedor."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import viz, xg

ctx = st.session_state["ctx"]

st.title("🎯 Modelo de xG propio")
st.caption(
    "Regresión logística sobre tres rasgos del tiro — distancia, ángulo y cabeza — "
    "entrenada en la competición cargada con validación cruzada. No pretende batir "
    "al xG de StatsBomb: mide cuánto explica un modelo mínimo y si está bien calibrado."
)

resumen, shots = ac.entrena_xg(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tiros (sin penaltis)", f"{resumen['n_shots']}")
c2.metric("Goles", f"{resumen['n_goals']}")
c3.metric("Brier propio", f"{resumen['brier_own']:.4f}")
c4.metric("Brier StatsBomb", f"{resumen['brier_sb']:.4f}")
c5.metric("Brier base", f"{resumen['brier_base']:.4f}")
st.caption(
    "Brier = error cuadrático medio de la probabilidad (más bajo, mejor). La base es "
    "predecir a todos los tiros la tasa media de gol: cualquier modelo digno debe batirla."
)

if resumen["in_sample"]:
    st.warning(
        "Pocos tiros para validación cruzada: las predicciones son in-sample y la calibración es orientativa."
    )

left, right = st.columns(2)
with left:
    ac.fig_and_download(
        viz.calibration_chart(
            xg.calibration_bins(shots["xg_own"], shots["goal"]),
            xg.calibration_bins(shots["sb_xg"], shots["goal"]),
            ctx["comp_label"],
        ),
        "calibracion_xg.png",
    )
with right:
    ac.fig_and_download(viz.xg_scatter(shots, ctx["comp_label"]), "xg_propio_vs_proveedor.png")

st.markdown("#### Qué aprende el modelo")
coefs = pd.DataFrame(
    {
        "Rasgo": [xg.FEATURE_LABELS[f] for f in xg.FEATURES],
        "Coeficiente": [resumen["coef"].get(f, float("nan")) for f in xg.FEATURES],
    }
)
st.dataframe(
    coefs,
    use_container_width=True,
    hide_index=True,
    column_config={"Coeficiente": st.column_config.NumberColumn(format="%+.3f")},
)
st.markdown(
    "- **Distancia** con signo negativo: cuanto más lejos, menos probable el gol.\n"
    "- **Ángulo** con signo positivo: más portería a la vista, más gol.\n"
    "- **Cabeza** suele restar: a igualdad de posición, el remate de cabeza convierte menos."
)

with st.expander("Cómo se entrena (y qué no ve)"):
    st.markdown(
        """
- Tiros de la competición cargada sin penaltis ni tandas, como el resto del proyecto.
- Predicciones **out-of-fold** (validación cruzada estratificada): cada tiro se evalúa
  con un modelo que no lo vio, así la curva de calibración no se autoengaña.
- Los coeficientes mostrados se ajustan después sobre todos los tiros.
- **Lo que no ve**: presión del defensor, posición del portero, altura del balón,
  contexto de la jugada... — todo lo que sí usa el proveedor. Que el Brier propio se
  acerque al de StatsBomb con tres rasgos dice mucho de esos rasgos; superarlo no es
  el objetivo ni sería creíble.
"""
    )
