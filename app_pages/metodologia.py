"""Metodología: definición exacta de cada métrica y sus limitaciones."""

import streamlit as st

st.title("Metodología")
st.caption("Medir bien importa más que acumular gráficos. Esto es exactamente lo que se calcula.")

st.markdown(
    """
#### Métricas de jugador

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

#### Métricas de equipo

| Métrica | Definición |
|---|---|
| **Posesión** | Cuota de pases propios sobre el total de los partidos jugados |
| **npxG a favor / en contra** | xG sin penaltis generado y concedido, por partido |
| **PPDA** | Pases del rival en su zona de construcción (su 60 % inicial) por cada acción defensiva propia (entradas, intercepciones, faltas) en campo contrario. Más bajo = presión más intensa |
| **Presiones/partido** | Eventos de presión de StatsBomb por partido |

#### Encaje jugador–equipo

| Componente | Definición |
|---|---|
| **Estilo del equipo** | Tres ejes z-score entre equipos: posesión, presión (PPDA invertido + presiones/partido) y verticalidad (cuota de pases progresivos en juego) |
| **Rasgos del jugador** | Métricas per-90 estandarizadas (z-score) dentro de su grupo posicional |
| **Componente de estilo** | `z_equipo · afinidad · z_jugador`, con la matriz de afinidad documentada en `fit.py` (un equipo presionante demanda presiones y recuperaciones; uno posesivo, fiabilidad y progresión; uno vertical, conducción y regate) |
| **Mejora del puesto** | Percentil medio del jugador en las métricas clave de su grupo (las del radar) menos el nivel medio del mismo grupo en el equipo de destino |
| **Encaje (0-100)** | Percentil de la media de ambos componentes estandarizados dentro del conjunto comparado |

El encaje ordena candidatos *dentro de la competición cargada*; no considera
edad, precio, rol táctico fino ni contexto de club.

#### Limitaciones conocidas

- Los percentiles son válidos *dentro de la competición analizada*.
- En torneos cortos las métricas per-90 tienen alta varianza; el umbral de
  minutos mitiga pero no elimina el problema.
- La posesión por cuota de pases es una aproximación razonable, no la oficial.
- El grupo posicional agrupa roles distintos (un lateral y un central comparten
  grupo DF); el siguiente paso natural es percentilar por rol.
- Las fotos provienen de TheSportsDB y pueden faltar para algunos jugadores.

Detalle completo y código en el
[repositorio](https://github.com/joseadam03/futbol-analytics).
"""
)
