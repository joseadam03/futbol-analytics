"""Modelo de xG propio: cuánto añade el contexto sobre la pura geometría."""

import pandas as pd
import streamlit as st

import app_common as ac
from futbol_analytics import viz, xg

ctx = st.session_state["ctx"]

st.title("🎯 Modelo de xG propio")
st.caption(
    "Dos modelos entrenados sobre la competición cargada y comparados fuera de "
    "muestra: uno **geométrico** (distancia, ángulo, cabeza) y otro **contextual**, "
    "que añade presión, defensores en el cono de tiro y posición del portero."
)

resumen, shots = ac.entrena_xg(
    ctx["provider_key"], int(ctx["comp"]["competition_id"]), int(ctx["comp"]["season_id"])
)
gana = resumen["best_model"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tiros (sin penaltis)", f"{resumen['n_shots']}")
c2.metric("Goles", f"{resumen['n_goals']}")
c3.metric("Brier geométrico", f"{resumen['brier_base']:.4f}", delta="elegido" if gana == "base" else None)
c4.metric(
    "Brier contextual",
    f"{resumen['brier_ctx']:.4f}",
    delta="elegido" if gana == "contextual" else None,
)
c5.metric("Brier StatsBomb", f"{resumen['brier_sb']:.4f}")
st.caption(
    f"Brier = error cuadrático medio de la probabilidad; más bajo, mejor. Predecir a "
    f"todos la tasa media de gol da {resumen['brier_naive']:.4f}: ese es el listón mínimo. "
    "Las predicciones son *out-of-fold*, así que la comparación es honesta."
)

if not resumen["has_context"]:
    st.info(
        "Estos datos no traen contexto de tiro (freeze frames, presión), así que solo "
        "se entrena el modelo geométrico."
    )
elif gana == "base":
    st.warning(
        "**El contexto no compensa aquí.** Con esta muestra, añadir rasgos empeora la "
        "predicción fuera de muestra: el modelo geométrico gana y es el que usa la app. "
        "Más variables no es mejor por definición — con pocos tiros, sobreajustan."
    )
else:
    mejora = 100 * (resumen["brier_base"] - resumen["brier_ctx"]) / resumen["brier_base"]
    st.success(
        f"**El contexto aporta**: el modelo contextual mejora un {mejora:.1f} % el Brier "
        "del geométrico fuera de muestra, y es el que usa la app."
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
    [
        {"Rasgo": xg.FEATURE_LABELS.get(k, k), "Coeficiente": v}
        for k, v in sorted(resumen["coef"].items(), key=lambda kv: -abs(kv[1]))
    ]
)
st.dataframe(
    coefs,
    use_container_width=True,
    hide_index=True,
    column_config={"Coeficiente": st.column_config.NumberColumn(format="%+.3f")},
)
st.markdown(
    "Los rasgos están estandarizados, así que los coeficientes son comparables entre sí. "
    "Signo negativo = reduce la probabilidad de gol.\n"
    "- **Distancia** manda: cuanto más lejos, menos gol.\n"
    "- **Portero adelantado** sube el xG: si está lejos de su línea, hay más portería.\n"
    "- **Defensores en el cono** y **presión** restan; **distancia al defensor** suma.\n"
    "- **Cabeza** resta a igualdad de posición."
)

with st.expander("Cómo se entrena (y qué sigue sin ver)"):
    st.markdown(
        """
- Tiros de la competición cargada sin penaltis ni tandas.
- **Rasgos de contexto** desde el *freeze frame* de StatsBomb, que fotografía a los
  jugadores visibles en el instante del disparo: cuántos rivales caen dentro del
  triángulo tirador–poste–poste, a qué distancia está el defensor más cercano, y
  dónde está el portero (distancia a su portería y desvío respecto al eje del tiro).
  Se añaden presión sobre el tirador, mano a mano, remate de primeras y el patrón
  de juego de la posesión.
- **Validación anidada**: la fuerza de la regularización se elige por validación
  cruzada *dentro* de cada fold de entrenamiento, así que no contamina las
  predicciones out-of-fold. Sin esto, con pocos tiros el modelo contextual
  sobreajusta y rinde peor que el geométrico.
- **Selección automática**: gana el modelo con mejor Brier fuera de muestra. Que a
  veces gane el geométrico es información, no un fallo.
- **Lo que sigue sin ver**: la altura del balón, la trayectoria, el cuerpo del
  portero (solo su posición), la calidad del rematador y todo lo que pasó antes del
  freeze frame. StatsBomb modela parte de eso; por eso su Brier sigue siendo mejor.
"""
    )
