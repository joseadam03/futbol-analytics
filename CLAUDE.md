# Fútbol Analytics — memoria del proyecto

Herramienta de análisis y scouting de fútbol sobre StatsBomb open data (y,
opcionalmente, Wyscout/Sportmonks). Es el proyecto de portafolio de Jose Adam
Lerin para su búsqueda de trabajo como analista de datos / scout de fútbol:
cada decisión de producto está pensada para que un reclutador o un club vea
tanto el análisis como el código detrás.

## Principio rector: "nada inventado, todo verificable"

Todo el texto explicativo (fortalezas/debilidades, lectura de encaje,
narrativa de estilo de equipo...) se genera con reglas deterministas sobre
datos ya calculados (`narrative.py`, `fit.py`), nunca con un LLM ni con datos
inventados. Por la misma razón:

- **No hay datos de valor de mercado, contrato ni edad.** Se descartó a
  propósito (ver Encaje/fichajes): StatsBomb open data no los trae, y
  Transfermarkt vía scraping es legalmente dudoso y, según Jose, demasiado
  volátil para fiarse. Si se pide "como Transfermarkt", la respuesta es no.
- **No hay alineaciones/formaciones/sustituciones.** Los tipos de evento de
  StatsBomb para eso (`Starting XI`, `Substitution`, `tactics.formation`...)
  no están verificados en ningún sitio de este proyecto (ni tests, ni
  `FakeProvider`, ni código existente) y este entorno no tiene acceso de red
  a datos reales para comprobarlos. No se construye sobre esquemas sin
  verificar: mejor no tener la función que tenerla rota en silencio.
- Antes de fiarte de un campo "por sentido común", comprueba si ya se usa en
  el código (grep) o si hay un comentario que documente el formato real de
  StatsBomb. Ejemplo ya resuelto: las coordenadas de evento son siempre desde
  la perspectiva atacante del equipo del evento (portería rival en x=120),
  **no** coordenadas fijas del campo físico — está documentado en la
  cabecera de `teams.py`. Por eso `viz.match_shot_map` solo necesita voltear
  las coordenadas del visitante (no del periodo/mitad) para separar los dos
  ataques en un mismo gráfico.

## Explicaciones en lenguaje llano (para quien no es analista)

Instrucción explícita de Jose: todo el contenido debe entenderlo alguien que
no es analista. Patrón ya establecido y que hay que seguir en cualquier
página o gráfico nuevo:

- `narrative.metric_definition(col)` da la definición en una frase de
  cualquier métrica per-90 (con o sin sufijo `_pct`); se reutiliza en el PDF
  y en la app para que la misma métrica se explique igual en todos lados.
- Cada radar/mapa lleva un `st.caption(...)` o un `with st.expander(...)`
  justo debajo explicando qué es cada eje/color/tamaño (ver `jugador.py`,
  `comparar.py`, `partido.py`).
- `fit.py` etiqueta el realismo de un fichaje (`etiqueta_realismo`,
  columna "Realismo" en Encaje) para que una mejora de puesto enorme no se
  lea como una recomendación seria sin más (p. ej. "Messi a un equipo
  pequeño" queda marcado, no oculto).

## Arquitectura

- **Proveedores** (`src/futbol_analytics/providers/`): `StatsBombProvider`
  (datos reales, open data), `WyscoutProvider` (implementado, sin
  credenciales activas — necesita `WYSCOUT_CLIENT_ID`/`SECRET`),
  `FakeProvider` (liga sintética determinista, sin red: la usan los tests y
  el modo demo `FUTBOL_ANALYTICS_FAKE=1`). Contrato común en `base.py`.
  Añadir un proveedor = implementar `Provider` y registrarlo en
  `providers/__init__.py`.
- **Métricas y visualización**: `metrics.py` (per-90 + percentiles),
  `teams.py` (estilo/rendimiento de equipo, `team_match_stats` es el bloque
  reutilizable para todo lo "por partido"), `series.py` (evolución
  partido a partido, por equipo/jugador/partido concreto), `xg.py` (modelo
  de xG propio con contexto), `similarity.py`, `viz.py` (matplotlib +
  mplsoccer, paleta con tema claro/oscuro vía `use_theme`).
- **Informe-CV en PDF**: `report.py`, deliberadamente sin llamadas de red
  propias — la foto/escudo (`photos.py`/`crests.py`, ambos con caché en
  disco y tolerantes a fallos) los resuelve quien llama (`app_common.py` o
  los scripts de `scripts/`), nunca `report.py` en sí.
- **App Streamlit**: `streamlit_app.py` (sidebar + navegación) +
  `app_common.py` (estado compartido, todo cacheado con `st.cache_data`) +
  `app_pages/*.py`. Páginas actuales: Inicio, Buscador, Jugador, Comparar,
  Encaje (fit + centro de fichajes), Equipos, Informe de equipo, **Partido**
  (comparación local-visitante, mapa de tiros del partido, top jugadores),
  Competición, Secuencias, Evolución, Modelo xG, Metodología.

## Cómo validar antes de dar nada por terminado

```
make lint     # ruff check + ruff format --check + mypy (src, scripts, app_common.py, streamlit_app.py)
make test     # pytest con cobertura
make demo     # la app en local con la liga sintética, sin red ni descargas
```

- `app_pages/` no pasa por mypy (ver `make lint`), pero sí por los tests de
  interfaz: cada página nueva debe añadirse a `PAGINAS` en `tests/test_app.py`
  para el smoke test de AppTest (`FUTBOL_ANALYTICS_FAKE=1`, sin red).
- Para cambios visuales de verdad, además de AppTest arranca la app
  (`make demo` o `FUTBOL_ANALYTICS_FAKE=1 streamlit run ...`) y compruébalo
  con un navegador real — AppTest no pilla regresiones puramente visuales.
- Workflow habitual: implementar → `ruff format`/`ruff check` → `mypy` →
  `pytest` completo → verificación visual si aplica → commit → push a
  `main` → comprobar la CI (GitHub Actions, workflow `ci.yml`).

## Fuera del repo, a propósito

Los detalles de despliegue/infraestructura (dónde corre la demo, dominio,
certificados, cómo se pasan los secretos a la VM) **no se documentan aquí ni
en el README** — es información operativa que Jose pidió explícitamente
mantener fuera de cualquier cosa pública o versionada ("es solo para mí y la
VM", "no tienen por qué saberlo"). El README solo lleva la instrucción
genérica de Docker (`docker build` / `docker run`). Si hace falta ese
contexto, pregúntale a Jose directamente en el chat; no lo reconstruyas ni lo
añadas a ningún fichero del repo por iniciativa propia.
