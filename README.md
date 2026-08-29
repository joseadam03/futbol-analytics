# futbol-analytics

[![CI](https://github.com/joseadam03/futbol-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/joseadam03/futbol-analytics/actions/workflows/ci.yml)

Aplicación de análisis de rendimiento de jugadores sobre
[StatsBomb open data](https://github.com/statsbomb/open-data): métricas per-90,
percentiles por grupo posicional, comparador de jugadores, motor de similitud,
**encaje jugador–equipo**, **modelo de xG propio** e informe-CV en PDF — con
interfaz web, CLI y arquitectura preparada para más proveedores (Wyscout).

> Proyecto de portafolio. El objetivo no es acumular gráficos, sino medir bien:
> cada métrica está definida abajo, con sus supuestos y sus limitaciones.

## La app

```bash
pip install -r requirements.txt && pip install --no-deps -e .
streamlit run streamlit_app.py
```

¿Sin ganas de esperar a la primera descarga? `make demo` arranca al instante
sobre una liga sintética (`FUTBOL_ANALYTICS_FAKE=1`), sin red y con dos equipos
de estilos opuestos para que todas las páginas tengan algo que contar.

Multipágina, con navegación propia:

- **Inicio** — resumen de la competición y jugadores destacados.
- **Buscador** — localiza a cualquier jugador: si está en la competición cargada
  salta a su informe completo; si no está en los open data, muestra su ficha
  informativa vía TheSportsDB y enlaces para seguir el scouting fuera.
- **Jugador** — radar de percentiles per-90, mapas de campo (calor de toques,
  pases progresivos/clave, tiros con tamaño ∝ xG), perfiles similares con foto y
  botón para generar el **informe-CV en PDF de una página**.
- **Comparar** — radar superpuesto de dos jugadores (por defecto, el más similar)
  con tabla de valores y percentiles lado a lado.
- **Encaje** — motor de encaje jugador–equipo: a qué equipos les encaja un
  jugador y qué fichajes le encajan a un equipo, cruzando el estilo del equipo
  (posesión, presión, verticalidad) con los rasgos per-90 del jugador y la
  mejora que aporta al nivel del puesto (por **rol fino** y ponderada por
  minutos). Pesos ajustables, mapa de estilo de la competición, descarga en CSV
  y pool ampliable con otras competiciones ya cacheadas.
- **Equipos** — posesión, **PPDA** (intensidad de presión), npxG a favor y en
  contra por partido, y dispersión posesión vs. dominio.
- **Competición** — dispersión interactiva de todos los jugadores (ejes a elegir,
  tooltip con nombre) y tabla completa descargable en CSV.
- **Modelo xG** — regresión logística propia (distancia, ángulo, cabeza)
  entrenada sobre la competición con validación cruzada, contrastada con el xG
  de StatsBomb: curva de calibración, Brier score y coeficientes interpretables.
- **Metodología** — definición exacta de cada métrica dentro de la propia app.
- **Modo claro y oscuro**: los gráficos siguen el tema del usuario con una paleta
  validada para accesibilidad y daltonismo en ambas variantes.
- Todos los gráficos con botón de **descarga en PNG** para presentaciones.
- Fotos de jugadores vía TheSportsDB (gratuita; puede faltar alguna).

También en Docker:

```bash
docker build -t futbol-analytics .
docker run -p 8501:8501 futbol-analytics
```

## El CLI

Para generar un informe estático (PNGs + CSVs) de cualquier jugador:

```bash
python scripts/player_report.py --player "Messi"
python scripts/player_report.py --player "Aitana" --competition 72 --season 107
```

| Salida | Contenido |
|---|---|
| `radar.png` | Percentiles per-90 frente a jugadores de su mismo grupo posicional |
| `mapa_calor.png` | Densidad de toques sobre el campo |
| `mapa_pases.png` | Pases progresivos y pases que generaron tiro |
| `mapa_tiros.png` | Tiros sin penaltis, tamaño proporcional al xG |
| `informe.pdf` | **Informe-CV de una página**: cabecera, radar, los tres mapas, similares y mejores destinos |
| `similares.csv` | Top-10 jugadores con el perfil estadístico más parecido |
| `metricas_competicion.csv` | Tabla completa de métricas de toda la competición |

Por defecto se analiza el Mundial 2022 (`--competition 43 --season 106`). La
primera descarga de una competición se cachea en `data/cache/` y las siguientes
ejecuciones son instantáneas; `make warm` la precalienta de antemano (útil antes
de una demo o en un despliegue).

## Proveedores de datos

`src/futbol_analytics/providers/` define un contrato común (`base.py`): las
métricas y visualizaciones consumen un esquema de eventos normalizado, de modo
que añadir una fuente nueva no toca nada más.

- **StatsBomb open data** — implementado, con caché local.
- **Wyscout** — interfaz preparada; requiere credenciales de la API de Hudl
  (`WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET`) e implementar el mapeo de
  eventos documentado en `providers/wyscout.py`.
- **Demo (liga sintética)** — datos generados, deterministas y sin red. Se activa
  con `FUTBOL_ANALYTICS_FAKE=1` y es lo que usan los tests de interfaz para
  renderizar la app entera en segundos.

## Metodología

Reglas globales: se excluyen las tandas de penaltis (periodo 5) de todos los
cálculos, y los penaltis dentro del juego de las métricas de tiro.

- **Minutos jugados** — derivados de las alineaciones oficiales de StatsBomb
  (titularidad, cambios y expulsiones), no estimados desde eventos. Todas las
  métricas de volumen se normalizan a 90 minutos y los percentiles se calculan
  solo entre jugadores con un mínimo de minutos (180 por defecto).
- **npxG** — xG de StatsBomb acumulado, sin penaltis. `npxG/tiro` mide la
  calidad media de las ocasiones que genera el jugador.
- **xA (real)** — cada pase clave se enlaza con el tiro que generó mediante
  `shot_key_pass_id` y hereda su xG. No es la aproximación "asistencias
  esperadas = asistencias": mide la calidad del tiro generado, lo marque o no
  el compañero.
- **Pase/conducción progresiva** — acción que reduce la distancia del balón a
  la portería rival en al menos un 25 % (portería en `x=120, y=40`). Se
  excluyen saques de esquina, faltas, bandas y saques de puerta o de centro.
  Las conducciones exigen además un desplazamiento mínimo de 5 unidades para
  filtrar ruido.
- **Entradas+Intercepciones ajustadas por posesión (PAdj)** — un jugador de un
  equipo con 65 % de posesión tiene muchas menos oportunidades de defender que
  uno de un equipo con 35 %. Se aplica el factor clásico
  `0.5 / (1 − posesión propia)`, con la posesión estimada por cuota de pases.
  Comparar acciones defensivas brutas entre equipos de posesión dispar es un
  error habitual; este ajuste lo corrige de forma transparente.
- **Toques en el área** — eventos con balón (pase, tiro, conducción, regate,
  recepción) dentro del área rival.
- **Percentiles** — rango percentil dentro del grupo posicional (GK/DF/MF/FW),
  asignado por la posición más frecuente del jugador en los eventos. Además se
  deriva un **rol fino** (portero, central, lateral, pivote, interior,
  mediapunta, extremo, delantero) que usa el motor de encaje.
- **Jugadores similares** — z-score de cada métrica per-90 dentro del grupo
  posicional y similitud de coseno entre perfiles: compara la *forma* del
  perfil (a qué se dedica el jugador), no su volumen bruto.
- **Encaje jugador–equipo** — el estilo del equipo (posesión, presión,
  verticalidad) en z-scores de la competición, cruzado con los rasgos per-90
  estandarizados del jugador vía una matriz de afinidad documentada en `fit.py`,
  más la mejora que aporta al nivel del puesto (rol fino, ponderado por minutos).
- **xG propio** — regresión logística sobre distancia, ángulo de portería y
  remate de cabeza, entrenada en la competición cargada. Las predicciones que se
  muestran son *out-of-fold* (validación cruzada estratificada), así que la curva
  de calibración y el Brier score no están medidos sobre los datos de ajuste.

### Limitaciones conocidas

- Los open data cubren competiciones concretas, no el fútbol de clubes actual
  completo; los percentiles son *dentro de esa competición*.
- En torneos cortos (un Mundial son como mucho 7 partidos) las métricas per-90
  tienen mucha varianza; el umbral de minutos mitiga pero no elimina esto.
- La posesión por cuota de pases es una aproximación razonable, no la posesión
  oficial.
- Los percentiles siguen calculándose por grupo posicional; el rol fino se usa
  hoy en el encaje, y percentilar por rol es el siguiente paso natural.
- El pool multi-competición del encaje estandariza dentro de cada competición,
  pero no corrige diferencias de nivel entre ligas: es orientativo.
- El xG propio ve tres rasgos; el del proveedor ve presión, portero y contexto.
  El ejercicio es de transparencia y calibración, no de batir a StatsBomb.

## Estructura

```
streamlit_app.py      # entrada de la app (navegación multipágina)
app_common.py         # estado compartido: carga de datos, sidebar, descargas
app_pages/            # Inicio · Buscador · Jugador · Comparar · Encaje · Equipos · Competición · Modelo xG · Metodología
src/futbol_analytics/
  providers/          # contrato común + StatsBomb + Wyscout (preparado) + demo sintética
  metrics.py          # métricas per-90 de jugador, PAdj, percentiles, roles
  teams.py            # métricas de equipo: posesión, PPDA, npxG a favor/en contra
  similarity.py       # motor de jugadores similares
  fit.py              # motor de encaje jugador–equipo (estilo × rasgos + mejora del puesto)
  xg.py               # modelo de xG propio y su calibración
  report.py           # informe-CV de una página en PDF
  viz.py              # radar, mapas, mapa de estilo, calibración (tema claro/oscuro)
  tsdb.py             # cliente de TheSportsDB (validación estricta + circuito de corte)
  photos.py           # fotos de jugadores (TheSportsDB, con caché)
  paths.py            # rutas de caché, configurables por entorno
scripts/
  player_report.py    # CLI: informe estático de un jugador (PNGs, CSVs y PDF)
  warm_cache.py       # precalienta la caché de una competición
tests/                # unitarios, de humo y de interfaz (AppTest) — siempre sin red
.github/workflows/    # CI: lint+formato, tipos, auditoría, tests, Docker y publicación
Dockerfile            # imagen multi-stage, usuario sin privilegios, healthcheck
Makefile              # make help: install, lint, test, run, demo, warm, docker-*, lock
uv.lock               # dependencias resueltas y fijadas (requirements*.txt se exportan de aquí)
```

## Desarrollo

```bash
make install   # dependencias fijadas + paquete editable + hooks de pre-commit
make lint      # ruff check + formato + mypy (lo mismo que la CI)
make test      # pytest con cobertura
make audit     # pip-audit sobre las dependencias fijadas
make run       # la app en local
make demo      # la app con la liga sintética, sin descargas
make help      # todos los objetivos
```

Las dependencias se resuelven con [uv](https://docs.astral.sh/uv/) y quedan
fijadas en `uv.lock`; `requirements.txt` y `requirements-dev.txt` se exportan
desde el lock (`make lock`) para que pip, Docker y la CI instalen exactamente
las mismas versiones.

La CI corre en Python 3.11–3.14 con permisos mínimos (`contents: read`, elevados
solo donde hacen falta) y cinco trabajos: **lint-test** (ruff, formato y pytest
con cobertura mínima del 80 %), **types** (mypy), **security** (`pip-audit`
sobre el lock), **docker** (build, smoke test del healthcheck y escaneo Trivy
informativo) y **publish**, que sube la imagen a GHCR en cada push a `main`
—etiquetada `latest` y por SHA— solo si todo lo anterior está en verde.
Dependabot mantiene al día pip, GitHub Actions y la imagen base.

Para el proveedor Wyscout, copia `.env.example` a `.env` y rellena las
credenciales (la app y el CLI cargan `.env` automáticamente). La caché de datos
se puede reubicar con `FUTBOL_ANALYTICS_CACHE` (útil en contenedores; la imagen
oficial ya lo hace) y precalentar con `make warm`.

## Hoja de ruta

- Proveedor Wyscout completo (mapeo de eventos al esquema común)
- Percentiles por rol, no solo en el encaje
- Informe de equipo (estilo de juego: ritmo, presión, progresión)
- Ajuste de nivel entre competiciones para el encaje multi-liga

## Créditos

Datos: StatsBomb open data (uso no comercial, [términos](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf)).
Visualización sobre campo: [mplsoccer](https://mplsoccer.readthedocs.io/).
Fotos de jugadores: [TheSportsDB](https://www.thesportsdb.com/) (API gratuita, uso no comercial).
