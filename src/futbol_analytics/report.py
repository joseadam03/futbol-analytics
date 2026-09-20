"""Informe-CV del jugador: foto de cabecera, radar, mapas reales, similares y destinos.

Plantilla oscura con foto de retrato, tipografía Inter (SIL OFL, empaquetada
en assets/fonts/) y paneles de mapas reales generados con matplotlib +
mplsoccer — nunca imágenes simuladas. La paleta (`_BG`/`_PANEL`/`_GRID`/
`_TEXT`/`_MUTED`/`_ACCENT`/`_RED`) y las coordenadas de cada sección están
calcadas de una referencia real que Jose pidió replicar — es deliberadamente
propia de este informe, no la de `viz.py` (que sigue siendo azul/naranja en
el resto de la app): este documento es un CV editorial para imprimir o
adjuntar, no una pantalla más de la app.

Todo el texto explicativo viene de narrative.py (reglas deterministas sobre
datos ya calculados), nunca inventado; el "percentil medio" del medidor es
la media real de los mismos percentiles que dibuja el radar, no un "Overall
Rating" inventado como el de la referencia. Tampoco lleva edad, altura, pie
preferido ni nacionalidad — no existen en StatsBomb open data (ver
CLAUDE.md) — ni las etiquetas cualitativas de "Tactical Profile" de la
referencia, que no son verificables a partir de los eventos; en su lugar,
el panel equivalente enseña un adelanto real de "Mejores destinos" (motor
de encaje), que la página 2 completa.

player_report_pdf genera dos páginas A4 verticales: la 1ª es la ficha visual
(foto, perfil, puntos fuertes/por mejorar, datos clave, radar+medidor,
mapas); la 2ª son perfiles similares y mejores destinos (motor de encaje),
que necesitan más espacio del que cabe sin apretar la 1ª página.

ficha_report_pdf (para jugadores fuera de los open data cargados, sin
eventos con coordenadas) usa la misma cabecera e identidad visual, pero
mantiene su flujo secuencial de una sola página: cada bloque calcula dónde
empieza el siguiente, así que una sección ausente no deja un hueco
reservado para ella.
"""

from __future__ import annotations

import gc
import io
import textwrap
from datetime import date
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Rectangle
from mplsoccer import Pitch, VerticalPitch
from PIL import Image
from scipy.ndimage import gaussian_filter

from . import fit, narrative, photos, similarity, viz
from .metrics import SET_PIECE_PASS_TYPES, is_progressive

PAGE_SIZE = (8.27, 11.69)  # A4 vertical, pulgadas

# fuentes propias (SIL OFL 1.1, ver assets/fonts/OFL.txt) registradas una
# vez al importar el módulo; plt.rc_context aplica la familia solo mientras
# se genera un informe, sin tocar el rcParams global del resto de la app.
_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
for _font_path in sorted(_FONTS_DIR.glob("*.ttf")):
    fm.fontManager.addfont(str(_font_path))
# el stub de matplotlib tipa rc_context() con un Literal enorme de las claves
# de rcParams conocidas; un dict[str, ...] normal (aunque las claves sean
# válidas de sobra en tiempo de ejecución) no es subtipo de eso por la
# invarianza de dict — de ahí el "type: ignore[arg-type]" en las dos llamadas.
_FONT_CONTEXT = {"font.family": "sans-serif", "font.sans-serif": ["Inter", "DejaVu Sans"]}

# npxG/xA son tasas pequeñas (casi siempre < 1): con un decimal se verían
# como "0.0" para casi cualquier jugador. El resto de métricas per-90 del
# radar son recuentos (pases, presiones...) donde un decimal ya distingue.
_TWO_DECIMAL_METRICS = {"npxg_p90", "xa_p90"}

# Paleta propia del informe (no la de viz.py): esta plantilla es un
# documento editorial aparte para imprimir/adjuntar, con una identidad
# visual concreta que Jose pidió replicar de una referencia real —
# distinta a propósito del azul/naranja del resto de la app.
_BG = "#071012"
_PANEL = "#0C1719"
_GRID = "#243337"
_TEXT = "#E9F0EF"
_MUTED = "#8FA3A4"
_ACCENT = "#37E58C"
_RED = "#FF655D"


def _fmt_metric_value(prow: pd.Series, raw_col: str) -> str:
    v = prow.get(raw_col)
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.2f}" if raw_col in _TWO_DECIMAL_METRICS else f"{v:.1f}"


def _truncate(text: str, maxlen: int = 56) -> str:
    """Corta una línea antes de que invada la columna o el hueco vecino.

    Nombres reales (p. ej. "Lionel Andrés Messi Cuccittini... Right Center
    Forward") son mucho más largos que los de prueba y sin esto se salen de
    su hueco.
    """
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def _panel_png(fig, dpi: int = 200) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _fetch_image(url: str | None) -> Image.Image | None:
    """Descarga y abre una imagen; None si no hay URL o falla (foto/escudo caídos no rompen el informe)."""
    if not url:
        return None
    data = photos.fetch_bytes(url)
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    except Exception:
        return None


def _es_recorte_transparente(img: Image.Image | None) -> bool:
    """True si la imagen trae canal alfa con transparencia real (no solo
    técnicamente RGBA pero opaca de borde a borde) — el recorte de jugador
    de TheSportsDB, a diferencia de una foto de agencia normal con fondo
    físico (como la de Aaron Mooy, JPG opaco pese a llevar un nombre de
    fichero parecido). Un 2% de píxeles con alfa por debajo de 250 basta
    para distinguir un recorte real de una imagen opaca con canal alfa
    accidental.
    """
    if img is None:
        return False
    if img.mode not in ("RGBA", "LA") and not (img.mode == "P" and "transparency" in img.info):
        return False
    alpha = np.asarray(img.convert("RGBA"))[:, :, 3]
    return bool((alpha < 250).mean() > 0.02)


def _photo_box(
    img: Image.Image | None, aspect_w: float, aspect_h: float, fade_frac: float = 0.55
) -> Image.Image:
    """Recorta la foto al aspect ratio de la caja (cover-fit, sin deformar) y funde
    su borde izquierdo con el fondo (scrim), para que el nombre pueda montarse
    encima y siga siendo legible sin depender de lo clara u oscura que sea la
    foto real.

    `aspect_w`/`aspect_h` son solo la proporción de la caja destino (en
    pulgadas de figura, p. ej. `photo_w_frac * PAGE_SIZE[0]`): aquí solo se
    recorta, nunca se redimensiona con PIL — matplotlib ya reescala con
    `interpolation="lanczos"` al dibujar (mismo patrón que el resto del
    informe para fotos pequeñas), así que forzar aquí un tamaño de píxeles
    fijo sería un resize redundante.

    Las fotos de jugador (TheSportsDB/Sportmonks) son retrato, mucho más
    altas que anchas, y la caja de cabecera es apaisada — recortar la altura
    centrado corta la coronilla y se queda solo con barbilla-a-pecho (visto
    en un informe real). Sin detección de cara, la aproximación es anclar el
    recorte casi arriba del todo (deja solo un margen pequeño de aire sobre
    la cabeza) y quitar el resto por abajo, que es donde suele estar el
    torso/uniforme, no la cara.

    Sin foto, un informe sigue siendo válido: rectángulo plano del color de
    panel en vez de un hueco vacío que desentone del resto de la cabecera.
    """
    bg = _hex_to_rgb(_PANEL)
    box_ratio = aspect_w / aspect_h
    if img is not None:
        # TheSportsDB sirve el recorte de jugador con fondo transparente
        # (RGBA). Image.convert("RGB") directo NO compone sobre nada: los
        # píxeles transparentes se quedan con el RGB que tuvieran debajo del
        # canal alfa, que en la práctica suele ser negro puro — un halo negro
        # rectangular alrededor del recorte en vez de fundirse con el fondo
        # oscuro del informe (visto en un informe real). Componer primero
        # sobre `bg` antes de aplanar a RGB es lo que faltaba.
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            canvas = Image.new("RGB", img.size, bg)
            canvas.paste(img, mask=img.split()[-1])
            img = canvas
        else:
            img = img.convert("RGB")
        src_ratio = img.width / img.height
        if src_ratio > box_ratio:
            new_w = int(img.height * box_ratio)
            x0 = (img.width - new_w) // 2
            img = img.crop((x0, 0, x0 + new_w, img.height))
        else:
            new_h = int(img.width / box_ratio)
            margen_superior = min(int(img.height * 0.02), img.height - new_h)
            img = img.crop((0, margen_superior, img.width, margen_superior + new_h))
    else:
        fallback_w = 1000
        img = Image.new("RGB", (fallback_w, int(fallback_w / box_ratio)), bg)

    arr = np.asarray(img).astype(float)
    box_w_px = arr.shape[1]
    fade_px = int(box_w_px * fade_frac)
    alpha_col = np.ones(box_w_px)
    if fade_px > 0:
        alpha_col[:fade_px] = np.linspace(0, 1, fade_px) ** 1.4
    bg_arr = np.array(bg, dtype=float)
    blended = arr * alpha_col[None, :, None] + bg_arr[None, None, :] * (1 - alpha_col[None, :, None])
    return Image.fromarray(blended.astype("uint8"))


def _embed_image(
    fig, url: str | None, pos: tuple[float, float, float, float], min_dpi: float = 140.0
) -> bool:
    """Incrusta una imagen (el escudo del equipo) si hay URL y se puede descargar.

    Devuelve si se dibujó, para que el llamante decida si reservar sitio
    para ella. Los avatares/escudos de TheSportsDB/Sportmonks a veces son
    pequeños (cientos de píxeles, no miles); estirarlos a la caja pedida los
    deja pixelados sin remedio — ningún filtro de interpolación inventa
    detalle que no existe. Si la resolución nativa no llega a `min_dpi`
    dentro de la caja, se reduce (centrada en el mismo hueco) hasta que sí
    se vea nítida, en vez de forzarla al tamaño completo.
    """
    img = _fetch_image(url)
    if img is None:
        return False

    x, y, w, h = pos
    fig_w_in, fig_h_in = fig.get_size_inches()
    dpi_nativo = min(img.width / (w * fig_w_in), img.height / (h * fig_h_in))
    if dpi_nativo < min_dpi:
        factor = dpi_nativo / min_dpi
        nuevo_w, nuevo_h = w * factor, h * factor
        x, y = x + (w - nuevo_w) / 2, y + (h - nuevo_h) / 2
        w, h = nuevo_w, nuevo_h

    ax = fig.add_axes((x, y, w, h))
    ax.imshow(img, interpolation="lanczos")
    ax.axis("off")
    return True


def _section_title(fig, x: float, y: float, text: str, width: float = 0.88) -> None:
    """Título de sección: versalitas pequeñas + línea divisoria fina."""
    fig.text(x, y, text.upper(), fontsize=8, fontweight="bold", color=_MUTED, va="top")
    fig.add_artist(
        plt.Line2D([x, x + width], [y - 0.006, y - 0.006], transform=fig.transFigure, color=_GRID, lw=0.8)
    )


def _t(
    ax,
    x: float,
    y: float,
    s: str,
    size: float = 9,
    color: str = _TEXT,
    weight: str = "normal",
    ha: str = "left",
    va: str = "center",
) -> None:
    """Texto en coordenadas relativas (0-1) del propio `ax` — igual que la
    plantilla de referencia (texto sin recortar: puede salirse de su axes
    hacia arriba/abajo, que es justo lo que usa la referencia para separar
    título/subtítulo sin crear un axes por línea)."""
    ax.text(x, y, s, fontsize=size, color=color, weight=weight, ha=ha, va=va, transform=ax.transAxes)


def _fit_name_lines(
    fig, ax, display: str, max_width_frac: float, max_size: float = 46, min_size: float = 20
) -> tuple[list[str], float]:
    """Nombre en mayúsculas, en 1-2 líneas (primera palabra / resto, como
    en la referencia), con el tamaño de letra más grande que quepa en
    `max_width_frac` del ancho de `ax` — medido con el renderer real
    (misma técnica que el resto del informe), no a ojo: un apellido largo
    no puede desbordar sobre la foto."""
    palabras = display.upper().split()
    lineas = [palabras[0], " ".join(palabras[1:])] if len(palabras) > 1 else [palabras[0]]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_w_px = ax.get_window_extent(renderer=renderer).width
    size = max_size
    while size > min_size:
        ancho_px = 0.0
        for linea in lineas:
            txt = ax.text(0, 0, linea, fontsize=size, weight="bold", transform=ax.transAxes)
            ancho_px = max(ancho_px, txt.get_window_extent(renderer=renderer).width)
            txt.remove()
        if ancho_px / ax_w_px <= max_width_frac:
            break
        size -= 2
    return lineas, size


def _panel_ax(fig, x: float, y: float, w: float, h: float):
    """Panel plano (sin borde ni esquinas redondeadas) — mismo patrón que
    `add_panel` de la referencia: un axes normal con su color de fondo,
    ejes ocultos, usado como lienzo para texto/formas en vez de un gráfico."""
    ax = fig.add_axes((x, y, w, h))
    ax.set_facecolor(_PANEL)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    return ax


def _panel_radar_polar(ax, labels: list[str], values: list[float]) -> None:
    """Radar en matplotlib polar puro (no mplsoccer.Radar) — mismo estilo
    visual que la referencia, alimentado con percentiles reales."""
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles_closed = angles + angles[:1]
    values_closed = values + values[:1]
    ax.set_facecolor(_PANEL)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels([])
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=4.6, color=_MUTED)
    ax.tick_params(axis="x", pad=1.5)
    ax.grid(color=_GRID, lw=0.6)
    ax.plot(angles_closed, values_closed, color=_ACCENT, lw=1.7)
    ax.fill(angles_closed, values_closed, color=_ACCENT, alpha=0.16)
    ax.spines["polar"].set_color(_GRID)


def _hero_band(
    fig,
    name: str,
    subtitle: str,
    info_items: list[tuple[str, str]],
    photo_url: str | None,
    crest_url: str | None,
    hero_h: float,
    photo_x0: float,
    photo_w: float,
) -> float:
    """Cabecera: nombre + lista vertical de datos a la izquierda, foto de
    retrato (alta, no apaisada — a diferencia de una foto de jugador real,
    que es más alta que ancha) en `(photo_x0, photo_w)`, con un fundido
    corto solo en su borde izquierdo para que no invada la columna de datos.
    Devuelve la y donde puede empezar el resto de la página (justo bajo el
    borde inferior de la foto).
    """
    # margen superior de página (0.02) igual que el resto del informe:
    # sin él, la foto tocaba el borde físico de la hoja — la coronilla
    # quedaba literalmente en el canto, visto en un informe real.
    top_margin = 0.02
    photo_img = _photo_box(
        _fetch_image(photo_url), photo_w * PAGE_SIZE[0], hero_h * PAGE_SIZE[1], fade_frac=0.22
    )
    ax_photo = fig.add_axes((photo_x0, 1 - top_margin - hero_h, photo_w, hero_h))
    ax_photo.imshow(photo_img, interpolation="lanczos")
    ax_photo.axis("off")

    # espaciado relativo a hero_h (no offsets fijos): esta cabecera sirve
    # tanto para la banda grande de player_report_pdf como para la más baja
    # de ficha_report_pdf, y una lista de datos con offsets pensados para
    # una banda alta se saldría por debajo de una banda baja.
    top = 1 - 0.028
    fig.text(
        0.055,
        top,
        "INFORME DE JUGADOR · FUTBOL-ANALYTICS",
        fontsize=7,
        fontweight="bold",
        color=_ACCENT,
        va="top",
    )
    cursor = top - 0.038
    fig.text(0.05, cursor, _truncate(name, 17), fontsize=27, fontweight="bold", color=_TEXT, va="top")
    cursor -= 0.05
    if subtitle:
        fig.add_artist(
            Rectangle((0.055, cursor), 0.007, 0.013, transform=fig.transFigure, color=_ACCENT, lw=0)
        )
        fig.text(
            0.068, cursor - 0.002, subtitle.upper(), fontsize=8.5, fontweight="bold", color=_TEXT, va="top"
        )
        cursor -= 0.045

    # fijo, no proporcional al hueco disponible: con poco hueco (banda baja
    # de ficha_report_pdf) un row_h flexible podía quedar por debajo de lo
    # que el propio texto necesita (valor a fontsize 10 + su línea), y la
    # siguiente etiqueta se dibujaba encima del valor anterior.
    row_h = 0.032
    info_y = cursor
    crest_size = 0.024
    crest_pos = (0.055, info_y - 0.011 - 0.015, crest_size, crest_size * PAGE_SIZE[0] / PAGE_SIZE[1])
    crest_drawn = _embed_image(fig, crest_url, crest_pos, min_dpi=90.0)

    for i, (label, value) in enumerate(info_items):
        y = info_y - i * row_h
        fig.text(0.055, y, label.upper(), fontsize=6.5, fontweight="bold", color=_MUTED, va="top")
        text_x = 0.055 + crest_size + 0.012 if (i == 0 and crest_drawn) else 0.055
        fig.text(
            text_x, y - 0.017, _truncate(value, 18), fontsize=10, fontweight="bold", color=_TEXT, va="top"
        )

    # lo que se devuelve es seguro para el resto de la página tanto si la
    # lista de datos acaba más abajo que la foto (banda baja, varios ítems)
    # como al revés (banda alta): manda el que sobresalga más.
    info_bottom = info_y - len(info_items) * row_h
    return min(1 - top_margin - hero_h, info_bottom) - 0.03


def _mini_pitch(figsize: tuple[float, float] = (3.5, 2.5)):
    # fondo _BG, no _PANEL: en la referencia los mapas van directos sobre
    # el fondo de página, sin tarjeta propia alrededor.
    pitch = Pitch(pitch_type="statsbomb", pitch_color=_BG, line_color=_GRID, linewidth=1)
    fig, ax = pitch.draw(figsize=figsize)
    fig.set_facecolor(_BG)
    return pitch, fig, ax


def _report_player_events(events: pd.DataFrame, player: str) -> pd.DataFrame:
    ev = events[(events["player"] == player) & (events["period"] <= 4)]
    return ev[ev["location"].notna()]


def _panel_heatmap(events: pd.DataFrame, player: str):
    ev = _report_player_events(events, player)
    touches = ev[ev["type"].isin(["Pass", "Shot", "Carry", "Dribble", "Ball Receipt*"])]
    x = touches["location"].str[0].astype(float)
    y = touches["location"].str[1].astype(float)
    pitch, fig, ax = _mini_pitch()
    if len(x) >= 2:
        stats = pitch.bin_statistic(x, y, statistic="count", bins=(30, 20))
        stats["statistic"] = gaussian_filter(stats["statistic"], 1.5)
        pitch.heatmap(stats, ax=ax, cmap="turbo", edgecolors="none", zorder=0, alpha=0.85)
    return fig


def _touch_stats(events: pd.DataFrame, player: str) -> tuple[float, float, float, float] | None:
    """Centroide (dónde juega de media) y dispersión (cuánto se mueve) de
    sus toques — mismo criterio de "toque" que _panel_heatmap. Base real
    y verificable tanto para el punto del mini-campo como para las
    etiquetas del perfil táctico (nunca una zona puesta a mano)."""
    ev = _report_player_events(events, player)
    touches = ev[ev["type"].isin(["Pass", "Shot", "Carry", "Dribble", "Ball Receipt*"])]
    if len(touches) < 1:
        return None
    x = touches["location"].str[0].astype(float)
    y = touches["location"].str[1].astype(float)
    return float(x.mean()), float(y.mean()), float(x.std(ddof=0)), float(y.std(ddof=0))


def _panel_position_pitch(events: pd.DataFrame, player: str):
    """Punto de "dónde juega": centroide real de sus toques, no una zona
    puesta a ojo. Se dibuja con `scatter` (marcador circular en puntos de
    pantalla) y no con un `Circle` en coordenadas de datos, precisamente
    para no arrastrar la distorución de aspect ratio de un eje no
    cuadrado en pulgadas."""
    stats = _touch_stats(events, player)
    pitch, fig, ax = _mini_pitch(figsize=(2.3, 1.55))
    if stats is not None:
        cx, cy, _, _ = stats
        for size, alpha in ((950, 0.12), (480, 0.25), (150, 0.95)):
            ax.scatter([cx], [cy], s=size, color=_ACCENT, alpha=alpha, zorder=3, linewidths=0)
    return fig


#: umbrales en coordenadas StatsBomb (campo 120×80, siempre en la
#: perspectiva atacante del equipo del evento — ver cabecera de teams.py)
#: para las etiquetas del perfil táctico: tercios de largo y de ancho.
_TERCIO_X = (40.0, 80.0)
_TERCIO_Y = (26.67, 53.33)


def _perfil_tactico(
    events: pd.DataFrame, player: str, rol_o_grupo: str, pass_pct: float | None
) -> list[tuple[str, str]]:
    """Filas del bloque "Perfil táctico": reglas deterministas sobre datos
    ya calculados (mismo espíritu que narrative.py/fit.py), nunca texto
    generado. "Posición principal" ya es un dato; el resto son cortes de
    la posición media y de la dispersión reales de sus toques, y del %
    de pase ya calculado — ver los umbrales en _TERCIO_X/_TERCIO_Y."""
    stats = _touch_stats(events, player)
    if stats is None:
        return [
            ("Posición principal", rol_o_grupo),
            ("Altura recepción", "—"),
            ("Ocupación", "—"),
            ("Movimiento", "—"),
            ("Juego asociativo", "—"),
        ]
    cx, cy, std_x, std_y = stats
    if cx < _TERCIO_X[0]:
        altura = "Tercio defensivo"
    elif cx < _TERCIO_X[1]:
        altura = "Tercio medio"
    else:
        altura = "Tercio de ataque"
    if cy < _TERCIO_Y[0]:
        banda = "Banda izquierda"
    elif cy < _TERCIO_Y[1]:
        banda = "Zona central"
    else:
        banda = "Banda derecha"
    # dispersión combinada (norma de las desviaciones en x e y) frente al
    # umbral: un jugador "posicional" se mueve dentro de una zona acotada;
    # uno "itinerante" aparece en puntos muy distintos del campo.
    dispersion = (std_x**2 + std_y**2) ** 0.5
    movimiento = "Itinerante" if dispersion > 18.0 else "Posicional"
    if pass_pct is None:
        asociativo = "—"
    elif pass_pct >= 85:
        asociativo = "Alto"
    elif pass_pct >= 70:
        asociativo = "Medio"
    else:
        asociativo = "Bajo"
    return [
        ("Posición principal", rol_o_grupo),
        ("Altura recepción", altura),
        ("Ocupación", banda),
        ("Movimiento", movimiento),
        ("Juego asociativo", asociativo),
    ]


def _panel_passing_map(events: pd.DataFrame, player: str):
    """Pases clave/asistencia (naranja) frente al resto (gris) — distinto de
    _panel_progressive_map, que se centra en la progresión, no en el remate.
    """
    ev = _report_player_events(events, player)
    passes = ev[(ev["type"] == "Pass") & ev["pass_end_location"].notna()].copy()
    key_mask = pd.Series(False, index=passes.index)
    for c in ("pass_shot_assist", "pass_goal_assist"):
        if c in passes.columns:
            key_mask |= passes[c].eq(True)
    key = passes[key_mask]
    others = passes[~key_mask]

    pitch, fig, ax = _mini_pitch()
    for df, color, alpha, lw, z in ((others, _MUTED, 0.35, 1.2, 1), (key, _ACCENT, 0.85, 2.2, 2)):
        if df.empty:
            continue
        pitch.lines(
            df["location"].str[0].astype(float),
            df["location"].str[1].astype(float),
            df["pass_end_location"].str[0].astype(float),
            df["pass_end_location"].str[1].astype(float),
            comet=True,
            color=color,
            linewidth=lw,
            alpha=alpha,
            ax=ax,
            zorder=z,
        )
    return fig


def _panel_progressive_map(events: pd.DataFrame, player: str):
    """Pases progresivos (azul) y conducciones progresivas (naranja) — mismo
    umbral que metrics.player_metrics (is_progressive, min_advance=5.0 para
    conducciones)."""
    ev = _report_player_events(events, player)
    passes = ev[(ev["type"] == "Pass") & ev["pass_end_location"].notna()].copy()
    completed = passes[passes["pass_outcome"].isna()] if "pass_outcome" in passes.columns else passes
    open_play = (
        completed[~completed["pass_type"].isin(SET_PIECE_PASS_TYPES)]
        if "pass_type" in completed.columns
        else completed
    )
    prog_passes = open_play[is_progressive(open_play["location"], open_play["pass_end_location"])]

    if "carry_end_location" in ev.columns:
        carries = ev[(ev["type"] == "Carry") & ev["carry_end_location"].notna()].copy()
        prog_carries = carries[
            is_progressive(carries["location"], carries["carry_end_location"], min_advance=5.0)
        ]
    else:
        prog_carries = ev.iloc[0:0]

    pitch, fig, ax = _mini_pitch()
    for df, col_end, color, alpha in (
        (prog_passes, "pass_end_location", _ACCENT, 0.6),
        (prog_carries, "carry_end_location", _ACCENT, 0.75),
    ):
        if df.empty:
            continue
        pitch.lines(
            df["location"].str[0].astype(float),
            df["location"].str[1].astype(float),
            df[col_end].str[0].astype(float),
            df[col_end].str[1].astype(float),
            comet=True,
            color=color,
            linewidth=2.2,
            alpha=alpha,
            ax=ax,
            zorder=2,
        )
    return fig


def _panel_defensive_map(events: pd.DataFrame, player: str):
    """Presiones, entradas, intercepciones, bloqueos y despejes en un mapa.

    Tipos de evento verificados contra metrics.player_metrics: Pressure,
    duel_type == "Tackle", Interception, Block, Clearance.
    """
    ev = _report_player_events(events, player)
    duel_tackle = (
        ev["duel_type"] == "Tackle" if "duel_type" in ev.columns else pd.Series(False, index=ev.index)
    )
    kinds = [
        ("Presión", ev["type"] == "Pressure", _ACCENT),
        ("Entrada", duel_tackle, _ACCENT),
        ("Intercepción", ev["type"] == "Interception", _ACCENT),
        ("Bloqueo/despeje", ev["type"].isin(["Block", "Clearance"]), _MUTED),
    ]
    pitch, fig, ax = _mini_pitch()
    for _label, mask, color in kinds:
        sub = ev[mask.fillna(False)]
        if sub.empty:
            continue
        x = sub["location"].str[0].astype(float)
        y = sub["location"].str[1].astype(float)
        pitch.scatter(x, y, s=45, ax=ax, facecolor=color, edgecolor=_BG, linewidth=0.6, zorder=2)
    return fig


def _panel_touch_map(events: pd.DataFrame, player: str):
    """Dispersión de cada toque (sin suavizar) — complementa _panel_heatmap,
    que agrega la misma zona en una densidad borrosa; aquí se ve cada acción
    suelta, útil para detectar toques aislados que la densidad diluye."""
    ev = _report_player_events(events, player)
    touches = ev[ev["type"].isin(["Pass", "Shot", "Carry", "Dribble", "Ball Receipt*"])]
    x = touches["location"].str[0].astype(float)
    y = touches["location"].str[1].astype(float)
    pitch, fig, ax = _mini_pitch()
    if len(x):
        pitch.scatter(x, y, s=10, ax=ax, facecolor=_ACCENT, edgecolor="none", alpha=0.55, zorder=2)
    return fig


#: subtipos reales de `shot_outcome` que obligaron al portero a intervenir
#: o acabaron dentro (verificado contra datos reales de StatsBomb en
#: data/cache/events_43_106.pkl) — "a puerta", como en la referencia
#: (Goal/On target/Off target). "Blocked" no llegó a probar al portero
#: (lo paró un defensa antes), así que no cuenta como a puerta.
_SHOT_ON_TARGET = {"Goal", "Saved", "Saved to Post"}


def _panel_shot_map(events: pd.DataFrame, player: str):
    ev = _report_player_events(events, player)
    shots = ev[(ev["type"] == "Shot") & (ev.get("shot_type") != "Penalty")].copy()
    goals = shots[shots["shot_outcome"] == "Goal"]
    on_target = shots[shots["shot_outcome"].isin(_SHOT_ON_TARGET - {"Goal"})]
    off_target = shots[~shots["shot_outcome"].isin(_SHOT_ON_TARGET)]

    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color=_BG, line_color=_GRID, linewidth=1)
    fig, ax = pitch.draw(figsize=(3.1, 2.5))
    fig.set_facecolor(_BG)

    def _plot(df, **kw):
        if df.empty:
            return
        pitch.scatter(
            df["location"].str[0].astype(float),
            df["location"].str[1].astype(float),
            s=df["shot_statsbomb_xg"].fillna(0) * 500 + 25,
            ax=ax,
            zorder=2,
            **kw,
        )

    # mismo criterio que la referencia: gol en rojo, a puerta en blanco,
    # fuera en un tono neutro (antes todo lo que no era gol iba igual).
    _plot(off_target, facecolor=_MUTED, edgecolor="none", alpha=0.4)
    _plot(on_target, facecolor=_TEXT, edgecolor="none", alpha=0.75)
    _plot(goals, facecolor=_RED, edgecolor=_BG, linewidth=1, alpha=0.95)
    return fig


def _edad_desde_fecha(fecha: object) -> str:
    """Edad en años a partir de una fecha de nacimiento ISO (TheSportsDB
    `dateBorn` / Sportmonks `date_of_birth`) — calculada, no inventada.
    "—" si no hay fecha o no se puede parsear."""
    if not isinstance(fecha, str) or not fecha:
        return "—"
    try:
        nacimiento = date.fromisoformat(fecha[:10])
    except ValueError:
        return "—"
    hoy = date.today()
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return str(edad)


def player_report_pdf(
    table: pd.DataFrame,
    events: pd.DataFrame,
    player: str,
    comp_label: str,
    display: str | None = None,
    photo_url: str | None = None,
    crest_url: str | None = None,
    bio: dict | None = None,
) -> bytes:
    """PDF de dos páginas con el informe completo del jugador.

    Cabecera, tres columnas de datos y fila de mapas en coordenadas
    calcadas de una referencia real (posiciones exactas), con la paleta
    de esa misma referencia — pero solo con datos reales ya calculados en
    metrics.py/narrative.py/fit.py. `bio` (edad/nacionalidad/altura/pie)
    la resuelve quien llama, nunca esta función: mismo patrón que
    `photo_url`/`crest_url`, sin llamadas de red propias aquí — quien
    llama decide si acude solo a TheSportsDB o también a Sportmonks
    cuando la primera se queda corta (ver `app_common.bio_of`). Campo sin
    dato en ninguna fuente disponible → "—", nunca inventado. Sin
    "Overall Rating" inventado: el medidor sigue siendo el percentil
    medio real, igual que antes de esta plantilla.
    """
    with plt.rc_context(_FONT_CONTEXT):  # type: ignore[arg-type]
        prow = table[table["player"] == player].iloc[0]
        apodo = prow.get("nickname")
        display = display or (apodo if isinstance(apodo, str) and apodo else player)

        group = prow["position_group"]
        rol = prow.get("role")
        pool = str(rol).lower() + "s" if prow.get("pct_basis") == "role" and isinstance(rol, str) else None
        pool_desc = pool or str(group)

        posicion = prow["primary_position"]
        if isinstance(rol, str) and rol and rol != posicion:
            posicion = f"{posicion} ({rol})"

        resumen, fortalezas, debilidades = narrative.player_strengths(prow, pool_desc)
        # se calculan ya (no solo en la página 2): el panel "Mejores destinos"
        # de la fila inferior de la página 1 enseña un adelanto real
        destinos = fit.teams_for_player(table, events, player)
        destinos = destinos[~destinos["propio"]].head(5)

        fig1 = plt.figure(figsize=PAGE_SIZE)
        fig1.set_facecolor(_BG)

        # --- Foto hero: en el centro (datos a la izquierda, perfil a la
        # derecha — orden explícito de Jose), grande y protagonista como en
        # la referencia, pero sin solapar con el panel de perfil (la
        # referencia sí los solapa, pero ahí la foto es una toma editorial
        # con espacio en blanco pensado para eso; una foto de agencia real
        # como las que da TheSportsDB no lo tiene, y el panel opaco encima
        # se comía la mayor parte de la imagen — visto en un informe real).
        photo_x0, photo_y0, photo_w, photo_h = 0.325, 0.52, 0.36, 0.43
        ax_photo = fig1.add_axes((photo_x0, photo_y0, photo_w, photo_h))
        ax_photo.axis("off")
        photo_src = _fetch_image(photo_url)
        if _es_recorte_transparente(photo_src):
            # recorte real (fondo transparente): se planta tal cual, sin
            # recortar ni rellenar de un color de fondo — sin la caja
            # rectangular de antes, el jugador flota directamente sobre el
            # fondo oscuro de la página (pedido explícito de Jose: "quita
            # el fondo"). matplotlib encoge la caja al aspect ratio real de
            # la imagen (ax.set_facecolor("none") dentro de una figura ya
            # oscura, sin recorte de por medio) en vez de forzar el aspect
            # ratio apaisado de la caja original, pensado para fotos con
            # fondo real que si hay que recortar.
            assert photo_src is not None  # _es_recorte_transparente ya descarta None
            ax_photo.set_facecolor("none")
            ax_photo.imshow(np.asarray(photo_src.convert("RGBA")), interpolation="lanczos")
        else:
            photo_img = _photo_box(photo_src, photo_w * PAGE_SIZE[0], photo_h * PAGE_SIZE[1], fade_frac=0.0)
            ax_photo.imshow(photo_img, interpolation="lanczos")

        # --- Cabecera: nombre (1-2 líneas en mayúsculas, "JOSÉ" / "ADAM"
        # apiladas como en la referencia, no una sola línea) + posición.
        # Caja más alta que antes (0.175 vs. 0.07) para tener sitio: el
        # nombre grande de la referencia ocupa de verdad ~1/6 de la altura
        # de la página, comprobado con las coordenadas de píxel reales de
        # la imagen que compartió Jose, no a ojo.
        ax_h = fig1.add_axes((0.055, 0.79, 0.9, 0.175))
        ax_h.axis("off")
        _t(ax_h, 0, 0.94, "INFORME DE JUGADOR", 7, _MUTED, "bold")
        # ancho disponible antes de la foto (fracción del propio ax_h, que
        # ocupa 0.9 de la página) — un apellido largo no puede invadirla.
        nombre_max_frac = (photo_x0 - 0.02 - 0.055) / 0.9
        lineas_nombre, size_nombre = _fit_name_lines(fig1, ax_h, display, nombre_max_frac)
        if len(lineas_nombre) > 1:
            _t(ax_h, 0, 0.68, lineas_nombre[0], size_nombre, _TEXT, "bold")
            _t(ax_h, 0, 0.26, lineas_nombre[1], size_nombre, _TEXT, "bold")
        else:
            _t(ax_h, 0, 0.47, lineas_nombre[0], size_nombre, _TEXT, "bold")
        ax_h.add_patch(Rectangle((0, 0.05), 0.006, 0.05, transform=ax_h.transAxes, color=_ACCENT, lw=0))
        _t(ax_h, 0.018, 0.075, posicion.upper(), 10, _ACCENT, "bold")

        # --- "Dónde juega": mini-campo con un punto en su posición media
        # real (centroide de sus toques, no una zona puesta a ojo), arriba
        # a la derecha de la cabecera — pedido explícito de Jose.
        ax_pos = fig1.add_axes((photo_x0 + photo_w, 0.832, 0.272, 0.1385))
        ax_pos.axis("off")
        ax_pos.imshow(mpimg.imread(_panel_png(_panel_position_pitch(events, player))))

        # --- Columna de datos (izquierda, bajo la cabecera): un icono por
        # fila, mismo lenguaje visual que la referencia. Siempre son 4
        # filas fijas (no depende del jugador, a diferencia de PERFIL), así
        # que la caja se encoge una vez a una altura pensada para esas 4
        # filas — con la altura anterior (0.34) quedaba un hueco vacío
        # enorme debajo de "COMPARADO CON", muy visible al lado de la foto
        # que sí llega hasta abajo — "se ve mal, hace tan bajo", visto en
        # un informe real. El techo (arriba del todo) se mantiene fijo,
        # justo bajo la posición; se encoge por abajo.
        # biografía: de TheSportsDB, resuelta por quien llama (ver
        # docstring) — "—" en cualquier campo sin dato, nunca inventado.
        bio = bio or {}
        info_rows = [
            ("EDAD", _edad_desde_fecha(bio.get("nacimiento"))),
            ("NACIONALIDAD", str(bio.get("nacionalidad") or "—")),
            ("ALTURA", str(bio.get("altura") or "—")),
            ("PIE PREFERIDO", str(bio.get("pie") or "—")),
            ("EQUIPO", _truncate(str(prow["team"]), 20)),
            ("COMPETICIÓN", _truncate(comp_label, 20)),
        ]
        # 6 filas fijas ahora (antes 4): el hueco disponible es el mismo,
        # entre el borde de la cabecera (0.78) y el borde de DATOS CLAVE
        # (0.315 + 0.18 = 0.495, no 0.315 — ese es su y0, no su techo), así
        # que se reparten en ese hueco (0.265) en vez de escalar la altura
        # de la caja desde las 4 filas originales, que se salía por abajo
        # y quedaba tapado por el panel opaco de DATOS CLAVE.
        info_h = 0.265
        ax_info = fig1.add_axes((0.055, 0.78 - info_h, 0.25, info_h))
        ax_info.axis("off")
        # sin icono junto a cada fila (pedido explícito de Jose: aunque
        # geométricamente ya salían enteros, un icono lineal diminuto de
        # 20x20px se lee mal en la mayoría de casos reales).
        paso, valor_dy = 0.155, 0.0803
        yy = 0.87
        for k, v in info_rows:
            _t(ax_info, 0.02, yy, k, 5.5, _MUTED, "bold")
            _t(ax_info, 0.02, yy - valor_dy, v, 8, _TEXT, "bold")
            yy -= paso

        # --- Perfil + puntos fuertes + por mejorar (a la derecha de la
        # foto, nunca encima: ver comentario de la foto hero) ---
        # sin panel con fondo propio: en la referencia este bloque es texto
        # suelto directamente sobre el fondo de la página, sin ninguna caja
        # ni borde alrededor (comprobado a pixel contra la imagen de
        # referencia que compartió Jose) — por eso ahí un resumen corto no
        # "se ve mal" aunque deje mucho hueco debajo: no hay ningún
        # rectángulo cuyo borde inferior se note. Poner aquí un fondo de
        # panel fue el verdadero error, no la altura: una caja de fondo
        # fijo delataba tanto el hueco vacío (contenido corto) como, al
        # intentar arreglarlo encogiendo la caja al contenido, el desajuste
        # con la foto (que sigue bajando más que el panel). Con fondo
        # transparente y la misma caja fija que la foto (mismo borde
        # inferior en 0.52, igual que en la referencia), ambos problemas
        # desaparecen a la vez.
        ax_prof = fig1.add_axes((0.705, 0.52, 0.24, 0.30))
        ax_prof.set_facecolor("none")
        ax_prof.axis("off")
        _t(ax_prof, 0.06, 0.93, "PERFIL", 7, _ACCENT, "bold")
        n_lineas = 0
        if resumen:
            lineas = textwrap.wrap(resumen, width=35)
            n_lineas = len(lineas)
            for i, linea in enumerate(lineas):
                _t(ax_prof, 0.06, 0.83 - i * 0.075, linea, 7, _MUTED)
        yy = 0.83 - n_lineas * 0.075 - 0.06

        def _rasgos(titulo: str, y_start: float, signo: str, rasgos: list[tuple[str, str]]) -> float:
            _t(ax_prof, 0.06, y_start, titulo, 7, _ACCENT, "bold")
            y = y_start - 0.085
            for t, d in rasgos[:2]:
                _t(ax_prof, 0.06, y, signo, 9, _ACCENT, "bold")
                _t(ax_prof, 0.115, y, t, 7, _TEXT)
                y -= 0.05
                if d:
                    _t(ax_prof, 0.115, y, _truncate(d, 38), 5.8, _MUTED)
                    y -= 0.05
            return y

        yy = _rasgos("PUNTOS FUERTES", yy, "+", fortalezas)
        _rasgos("POR MEJORAR", yy - 0.01, "–", debilidades)

        # --- Datos clave / Radar / Percentil medio: fila de tres columnas ---
        key_metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])[:6]
        ax_data = _panel_ax(fig1, 0.055, 0.315, 0.40, 0.18)
        _t(ax_data, 0.04, 0.91, "DATOS CLAVE", 8, _TEXT, "bold")
        _t(ax_data, 0.42, 0.91, "VALOR", 5.5, _MUTED, "bold")
        _t(ax_data, 0.57, 0.91, "PERCENTIL", 5.5, _MUTED, "bold")
        yy = 0.76
        for col, label in key_metrics:
            raw_col = col[:-4] if col.endswith("_pct") else col
            valor = _fmt_metric_value(prow, raw_col)
            pct = float(prow[col]) if pd.notna(prow.get(col)) else 0.0
            _t(ax_data, 0.04, yy, label.replace("\n", " "), 5.5, _MUTED)
            _t(ax_data, 0.42, yy, valor, 6.2, _TEXT, "bold")
            # barra más corta que el hueco hasta el borde del panel (no hasta
            # 0.88 como antes): con percentil 100 el número quedaba encima
            # del final de la barra, visto en un informe real.
            ax_data.add_patch(
                FancyBboxPatch(
                    (0.57, yy - 0.025),
                    0.26,
                    0.035,
                    boxstyle="round,pad=0.002,rounding_size=.01",
                    fc=_GRID,
                    ec="none",
                )
            )
            ax_data.add_patch(
                FancyBboxPatch(
                    (0.57, yy - 0.025),
                    0.26 * pct / 100,
                    0.035,
                    boxstyle="round,pad=0.002,rounding_size=.01",
                    fc=_ACCENT,
                    ec="none",
                )
            )
            _t(ax_data, 0.97, yy, f"{pct:.0f}", 5.5, _ACCENT, "bold", ha="right")
            yy -= 0.115

        full_metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])
        # abreviado solo para las etiquetas angulares del radar: la caja es
        # estrecha (comparte fila con "datos clave" y "percentil medio") y
        # con el nombre completo la etiqueta se salía de su propio hueco e
        # invadía el panel vecino — el de la derecha además la tapaba a
        # media palabra, por dibujarse encima en el orden de capas (visto
        # en un informe real). Por nombre completo, no por palabra suelta:
        # más predecible que sustituir palabra a palabra. El nombre entero
        # ya está en la tabla "DATOS CLAVE" de al lado, así que aquí basta
        # con que se reconozca de un vistazo. viz.RADAR_METRICS conserva las
        # etiquetas completas para el resto de la app.
        _RADAR_ABBR = {
            "npxG": "npxG",
            "Tiros": "Tiros",
            "xA": "xA",
            "Pases clave": "Clave",
            "Regates": "Regate",
            "Toques en área": "T.área",
            "Conducciones progresivas": "Cond.",
            "Pases progresivos": "P.prog",
            "Presiones": "Pres.",
            "Entradas+Int. (PAdj)": "E+Int",
            "Recuperaciones": "Recup",
            "Bloqueos": "Bloq.",
            "Despejes": "Desp.",
            "Paradas": "Parada",
            "% de paradas": "% par.",
            "Salidas": "Salida",
            "Recogidas": "Recog.",
            "Puños": "Puños",
            "% de pase": "% pase",
        }

        def _abbr(label: str) -> str:
            limpio = label.replace("\n", " ")
            return _RADAR_ABBR.get(limpio, limpio[:6])

        radar_labels = [_abbr(lab) for _, lab in full_metrics]
        radar_values = [float(prow[c]) if pd.notna(prow.get(c)) else 0.0 for c, _ in full_metrics]
        avg_percentile = float(np.mean(radar_values)) if radar_values else 0.0

        # más bajo que datos clave/percentil medio (0.18): con esa altura,
        # incluso ya abreviadas, las etiquetas angulares más largas invadían
        # los paneles vecinos por los lados — a la derecha además tapadas a
        # media palabra, por quedar el panel de percentil medio encima en el
        # orden de capas (visto en un informe real). La altura, no el ancho,
        # es lo que fija el tamaño real del círculo+etiquetas en un polar de
        # matplotlib, así que bajarla es lo único que de verdad encoge todo
        # el conjunto y libera hueco lateral; medido con el renderer para
        # las 4 combinaciones de métricas (FW/MF/DF/GK), no a ojo.
        ax_radar = fig1.add_axes((0.49, 0.3375, 0.23, 0.135), projection="polar")
        _panel_radar_polar(ax_radar, radar_labels, radar_values)
        _t(ax_radar, 0.5, 1.24, "RADAR", 7, _TEXT, "bold", ha="center")

        # sin aspect fijo, un círculo de 0.30 en coordenadas de datos salía
        # ovalado (la caja no es cuadrada en pulgadas físicas) y además
        # autoescalaba casi hasta llenar los ejes, comiéndose el título de
        # encima — visto en un informe real. xlim/ylim explícitos + aspect
        # "equal" (adjustable="box", encoge la propia caja al cuadrado que
        # le cabe, centrada) lo dejan como un círculo real con margen.
        ax_rating = _panel_ax(fig1, 0.74, 0.315, 0.205, 0.18)
        ax_rating.set_xlim(0, 1)
        ax_rating.set_ylim(0, 1)
        ax_rating.set_aspect("equal", adjustable="box")
        _t(ax_rating, 0.08, 0.91, "PERCENTIL MEDIO", 6.5, _TEXT, "bold")
        ax_rating.add_patch(Circle((0.50, 0.50), 0.30, fill=False, lw=5, ec=_GRID))
        theta = np.linspace(0, 2 * np.pi, 100)
        portion = 2 * np.pi * avg_percentile / 100
        ax_rating.plot(
            0.5 + 0.30 * np.cos(theta[theta <= portion]),
            0.5 + 0.30 * np.sin(theta[theta <= portion]),
            color=_ACCENT,
            lw=5,
        )
        _t(ax_rating, 0.50, 0.53, f"{avg_percentile:.0f}", 18, _TEXT, "bold", ha="center")
        _t(ax_rating, 0.50, 0.37, "/100", 6, _MUTED, "bold", ha="center")

        # --- Mapas (6 paneles reales, sin tarjeta: directos sobre el fondo) ---
        mapas = [
            ("MAPA DE CALOR", _panel_heatmap(events, player)),
            ("PASSING MAP", _panel_passing_map(events, player)),
            ("ACCIONES PROGRESIVAS", _panel_progressive_map(events, player)),
            ("ACCIONES DEFENSIVAS", _panel_defensive_map(events, player)),
            ("MAPA DE TIROS", _panel_shot_map(events, player)),
            ("MAPA DE TOQUES", _panel_touch_map(events, player)),
        ]
        # más grandes que el 0.085 calcado de la referencia: sus mapas son
        # iconos vectoriales limpios pensados para verse pequeños, los
        # nuestros llevan datos reales (mapa de calor, dispersión de tiros)
        # que a ese tamaño se leían mal — "los mapas se ven enanos", visto
        # en un informe real. El hueco de sobra sale de encoger un poco la
        # fila de abajo (con balón/sin balón/perfil táctico).
        n = len(mapas)
        x0, gap = 0.055, 0.012
        w = (0.89 - gap * (n - 1)) / n
        map_h = 0.11
        for i, (label, pf) in enumerate(mapas):
            ax_m = fig1.add_axes((x0 + i * (w + gap), 0.185, w, map_h))
            ax_m.axis("off")
            _t(ax_m, 0, 1 + 0.0153 / map_h, label, 5.2, _TEXT, "bold")
            ax_m.imshow(mpimg.imread(_panel_png(pf)))

        # --- Con balón / Sin balón / Mejores destinos ---
        # un portero no se describe con las mismas métricas que un jugador
        # de campo (regates/entradas no dicen nada de su juego real, y le
        # faltan las suyas propias: paradas, salidas, recogidas) — mismo
        # fallo que ya tenía viz.RADAR_METRICS antes de este cambio, donde
        # GK usaba directamente la lista de DF.
        if group == "GK":
            con_balon = [
                ("Pases completados/90", "passes_cmp_p90"),
                ("% de pase", "pass_pct"),
                ("Pases progresivos/90", "prog_passes_p90"),
            ]
            sin_balon = [
                ("Paradas/90", "saves_p90"),
                ("% de paradas", "save_pct"),
                ("Salidas/90", "keeper_sweeper_p90"),
                ("Recogidas/90", "collected_p90"),
                ("Puños/90", "punches_p90"),
            ]
        else:
            con_balon = [
                ("Pases completados/90", "passes_cmp_p90"),
                ("% de pase", "pass_pct"),
                ("Pases progresivos/90", "prog_passes_p90"),
                ("Conducciones prog./90", "prog_carries_p90"),
                ("Regates/90", "dribbles_cmp_p90"),
                ("Pases clave/90", "key_passes_p90"),
                ("Asistencias/90", "assists_p90"),
                ("Toques en área/90", "touches_box_p90"),
            ]
            # 7, no 8: no hay una octava métrica defensiva ya calculada que
            # no sea repetir una de las seis de aquí — antes que inventar
            # una (ej. "duelos aéreos ganados", sin evento verificado en
            # este proveedor), se deja en 7.
            sin_balon = [
                ("Presiones/90", "pressures_p90"),
                ("Recuperaciones/90", "recoveries_p90"),
                ("Entradas/90", "tackles_p90"),
                ("Intercepciones/90", "interceptions_p90"),
                ("Entradas+Int. PAdj/90", "padj_tack_int_p90"),
                ("Bloqueos/90", "blocks_p90"),
                ("Despejes/90", "clearances_p90"),
            ]

        def _stat_panel(x: float, w_: float, titulo: str, filas: list[tuple[str, str]]) -> None:
            ax = _panel_ax(fig1, x, 0.065, w_, 0.105)
            _t(ax, 0.05, 0.88, titulo, 6.5, _TEXT, "bold")
            # paso repartido sobre el mismo rango que ocupan 5 filas a 0.15
            # (el caso normal de jugadores de campo): con menos filas —
            # portero, con listas más cortas de métricas reales— una fila
            # fija de 0.15 dejaba hueco vacío debajo, mismo problema que ya
            # se arregló en el panel PERFIL.
            paso = 0.60 / (len(filas) - 1) if len(filas) > 1 else 0.0
            for j, (label, raw_col) in enumerate(filas):
                y = 0.68 - j * paso
                pct = float(prow.get(f"{raw_col}_pct") or 0.0)
                _t(ax, 0.05, y, label, 5.2, _MUTED)
                # la barra deja hueco de sobra (hasta .78, no .88) antes del
                # valor a la derecha: con el percentil real como relleno
                # (no un tope arbitrario como .../100 o .../20), muchas filas
                # llegan cerca del 100 % y el número se pegaba a la barra.
                ax.add_patch(Rectangle((0.52, y - 0.018), 0.26, 0.032, fc=_GRID, ec="none"))
                ax.add_patch(Rectangle((0.52, y - 0.018), 0.26 * pct / 100, 0.032, fc=_ACCENT, ec="none"))
                _t(ax, 0.95, y, _fmt_metric_value(prow, raw_col), 5.2, _TEXT, "bold", ha="right")

        # 4 columnas (antes 3, sin "Impacto ofensivo"): mismo x0/ancho total
        # que la fila de mapas (0.055 a 0.945), repartido en 4 con el mismo
        # hueco entre columnas (0.012) que ya usa esa fila.
        col_w = (0.89 - 0.012 * 3) / 4
        c1, c2, c3, c4 = (0.055 + i * (col_w + 0.012) for i in range(4))

        _stat_panel(c1, col_w, "CON BALÓN", con_balon)
        _stat_panel(c2, col_w, "SIN BALÓN", sin_balon)

        # --- Impacto ofensivo: 6 insignias circulares con métricas por 90
        # ya calculadas (mismas fuentes que DATOS CLAVE/CON BALÓN, ningún
        # dato nuevo) — mismo lenguaje visual que PERCENTIL MEDIO (círculo
        # + número dentro) en miniatura.
        ax_ai = _panel_ax(fig1, c3, 0.065, col_w, 0.105)
        _t(ax_ai, 0.05, 0.88, "IMPACTO OFENSIVO", 6.5, _TEXT, "bold")
        ai_y_scale = (col_w * PAGE_SIZE[0]) / (0.105 * PAGE_SIZE[1])
        ai_metrics = [
            ("xG", "npxg_p90"),
            ("xA", "xa_p90"),
            ("P. clave", "key_passes_p90"),
            ("Tiros", "shots_p90"),
            ("T. área", "touches_box_p90"),
            ("Regates", "dribbles_cmp_p90"),
        ]
        ai_pos = [(0.2, 0.58), (0.5, 0.58), (0.8, 0.58), (0.2, 0.2), (0.5, 0.2), (0.8, 0.2)]
        r_badge = 0.09
        for (etiqueta, raw_col), (cx, cy) in zip(ai_metrics, ai_pos, strict=True):
            valor_raw = prow.get(raw_col)
            valor_num = float(valor_raw) if pd.notna(valor_raw) else 0.0
            ax_ai.add_patch(
                Ellipse(
                    (cx, cy),
                    r_badge * 2,
                    r_badge * 2 * ai_y_scale,
                    fill=False,
                    ec=_ACCENT,
                    lw=1.2,
                    transform=ax_ai.transAxes,
                )
            )
            _t(ax_ai, cx, cy + 0.012, f"{valor_num:.2f}", 6.0, _TEXT, "bold", ha="center")
            _t(ax_ai, cx, cy - r_badge * ai_y_scale - 0.05, etiqueta, 4.6, _MUTED, "bold", ha="center")

        # "Mejores destinos" sigue completo en la página 2 (motor de
        # encaje): este panel de la página 1 era solo un adelanto, y en la
        # referencia ese hueco es un "Perfil táctico" — reglas
        # deterministas sobre la posición media y el % de pase reales del
        # jugador (_perfil_tactico), no texto generado.
        ax_td = _panel_ax(fig1, c4, 0.065, col_w, 0.105)
        _t(ax_td, 0.05, 0.88, "PERFIL TÁCTICO", 6.5, _ACCENT, "bold")
        rol_compacto = rol if isinstance(rol, str) and rol else str(group)
        pass_pct_val = prow.get("pass_pct")
        pass_pct_val = float(pass_pct_val) if pd.notna(pass_pct_val) else None
        # etiqueta encima, valor debajo (no en la misma línea): la columna
        # es más estrecha que antes (4 columnas, no 3) y los valores de
        # este panel son texto ("Tercio de ataque"), no números cortos
        # como en CON BALÓN/SIN BALÓN — en la misma línea se pegaban.
        for j, (etiqueta, valor) in enumerate(_perfil_tactico(events, player, rol_compacto, pass_pct_val)):
            y = 0.74 - j * 0.15
            _t(ax_td, 0.05, y, etiqueta, 5.0, _MUTED)
            _t(ax_td, 0.05, y - 0.075, valor, 6.2, _TEXT, "bold")

        # --- Pie de página ---
        ax_foot = fig1.add_axes((0.055, 0.025, 0.89, 0.025))
        ax_foot.axis("off")
        _t(ax_foot, 0, 0.5, "FUTBOL-ANALYTICS · DATOS: STATSBOMB OPEN DATA", 5, _MUTED, "bold")
        _t(ax_foot, 1, 0.5, "NADA INVENTADO, TODO VERIFICABLE", 5, _MUTED, "bold", ha="right")

        # --- Página 2: perfiles similares y mejores destinos (motor de encaje) ---
        # 4, no 5: deja sitio a la nota de que "parecido" es de estilo, no de nivel
        # (destinos ya se calculó arriba, para el panel "Mejores destinos" de la página 1)
        sims = similarity.similar_players(table, player).head(4)

        fig2 = plt.figure(figsize=PAGE_SIZE)
        fig2.set_facecolor(_BG)
        fig2.text(
            0.055,
            0.955,
            "INFORME DE JUGADOR · FUTBOL-ANALYTICS",
            fontsize=7.5,
            fontweight="bold",
            color=_ACCENT,
            va="top",
        )
        fig2.text(0.055, 0.925, _truncate(display, 40), fontsize=16, fontweight="bold", color=_TEXT, va="top")

        y_top = 0.86
        _section_title(fig2, 0.055, y_top, "Perfiles similares", width=0.42)
        fig2.text(
            0.055,
            y_top - 0.02,
            "estilo parecido, no necesariamente el mismo nivel",
            fontsize=6.5,
            color=_MUTED,
            va="top",
        )
        for i, (_, s) in enumerate(sims.iterrows()):
            fig2.text(
                0.055,
                y_top - 0.05 - 0.024 * i,
                _truncate(
                    f"{s['similarity']:.3f}   {s['player']}  ({s['team']}, {s['primary_position']})", 60
                ),
                fontsize=9,
                color=_TEXT,
                va="top",
            )

        _section_title(fig2, 0.54, y_top, "Mejores destinos (encaje)", width=0.4)
        for i, (_, d) in enumerate(destinos.iterrows()):
            fig2.text(
                0.54,
                y_top - 0.032 - 0.024 * i,
                _truncate(
                    f"{d['encaje']:.0f}   {d['team']}  (estilo {d['estilo']:+.2f}, mejora {d['mejora_puesto']:+.0f})",
                    52,
                ),
                fontsize=9,
                color=_TEXT,
                va="top",
            )

        fig2.text(
            0.055,
            0.02,
            "FUTBOL-ANALYTICS · DATOS: STATSBOMB OPEN DATA · NADA INVENTADO, TODO VERIFICABLE",
            fontsize=5.5,
            color=_MUTED,
        )

        out = io.BytesIO()
        with PdfPages(out) as pdf_pages:
            pdf_pages.savefig(fig1, facecolor=fig1.get_facecolor())
            pdf_pages.savefig(fig2, facecolor=fig2.get_facecolor())
        plt.close(fig1)
        plt.close(fig2)
        data = out.getvalue()
    # este informe es el que más memoria mueve (foto de cabecera + seis
    # paneles con eventos de toda la competición); liberar cuanto antes en
    # vez de esperar al ciclo normal del GC importa en un contenedor con
    # RAM ajustada (Streamlit Community Cloud, ~1 GB)
    gc.collect()
    return data


def ficha_report_pdf(
    ficha: dict | None, ficha_sm: dict | None, query: str, crest_url: str | None = None
) -> bytes:
    """PDF de una página para un jugador fuera de los open data cargados.

    Sin eventos con coordenadas no hay radar, mapas ni encaje — pero la
    biografía de TheSportsDB y las estadísticas de temporada de Sportmonks
    (si hay token) ya bastan para una ficha presentable. `ficha` y
    `ficha_sm` pueden venir ambas a None si ningún servicio tuvo datos; el
    PDF se genera igual, dejándolo dicho.
    """
    with plt.rc_context(_FONT_CONTEXT):  # type: ignore[arg-type]
        candidatos_nombre = [
            n
            for n in ((ficha or {}).get("nombre"), (ficha_sm or {}).get("nombre"), query)
            if isinstance(n, str) and n.strip()
        ]
        # el nombre más largo suele ser el más completo (p. ej. la búsqueda del
        # usuario "Franculino Djú" frente a un display_name corto de la API)
        nombre = max(candidatos_nombre, key=len) if candidatos_nombre else query
        foto_url = (ficha or {}).get("foto") or (ficha_sm or {}).get("foto")
        temporadas = (ficha_sm or {}).get("temporadas") or []
        traspasos = (ficha_sm or {}).get("traspasos") or []
        fortalezas, a_vigilar = narrative.season_strengths(temporadas)

        fig = plt.figure(figsize=PAGE_SIZE)
        fig.set_facecolor(_BG)

        info_items = [
            (etiqueta, str(valor))
            for etiqueta, valor in (
                ("Equipo", (ficha or {}).get("equipo")),
                ("Posición", (ficha or {}).get("posicion")),
                ("Nacionalidad", (ficha or {}).get("nacionalidad")),
            )
            if valor
        ]
        hero_h = 0.20
        y = _hero_band(
            fig, nombre, "", info_items, foto_url, crest_url, hero_h=hero_h, photo_x0=0.73, photo_w=0.2
        )

        detalles = " · ".join(
            str(v)
            for v in (
                (ficha or {}).get("nacimiento"),
                (ficha or {}).get("lugar_nacimiento"),
                (ficha or {}).get("altura"),
            )
            if v
        )
        if detalles:
            fig.text(0.055, y, detalles, fontsize=8.5, color=_MUTED, va="top")
            y -= 0.03

        # justo bajo la cabecera, no al final donde sobre sitio: es la
        # conclusión antes que el detalle. Mismo patrón de dos columnas que
        # player_report_pdf — hechos directos de las temporadas de arriba,
        # no un ranking: sin eventos con coordenadas no hay percentiles
        # frente a rivales. "A vigilar" solo aparece si hay una tendencia
        # negativa real, no se fuerza como en el informe-CV.
        if fortalezas or a_vigilar:
            y_top = y
            _section_title(fig, 0.055, y_top, "Fortalezas", width=0.42)
            for i, (titulo, definicion) in enumerate(fortalezas):
                y_t = y_top - 0.024 - i * 0.033
                fig.text(0.055, y_t, titulo, fontsize=8.5, color=_TEXT, va="top")
                if definicion:
                    fig.text(
                        0.055, y_t - 0.013, _truncate(definicion, 68), fontsize=6.5, color=_MUTED, va="top"
                    )
            if a_vigilar:
                _section_title(fig, 0.54, y_top, "A vigilar", width=0.4)
                for i, (titulo, definicion) in enumerate(a_vigilar):
                    y_t = y_top - 0.024 - i * 0.033
                    fig.text(0.54, y_t, titulo, fontsize=8.5, color=_TEXT, va="top")
                    if definicion:
                        fig.text(
                            0.54,
                            y_t - 0.013,
                            _truncate(definicion, 68),
                            fontsize=6.5,
                            color=_MUTED,
                            va="top",
                        )
            max_items = max(len(fortalezas), len(a_vigilar), 1)
            y -= 0.024 + (max_items - 1) * 0.033 + 0.026 + 0.02

        fig.text(
            0.055,
            y,
            "Ficha de scouting compuesta a partir de fuentes públicas (biografía de TheSportsDB, "
            "estadísticas de temporada de Sportmonks). Al no ser un jugador de los open data "
            "cargados en la app, no hay eventos con coordenadas de jugada: sin ellos no se puede "
            "calcular radar de percentiles, mapas de calor/tiros/pases ni el motor de encaje.",
            fontsize=7.5,
            color=_MUTED,
            va="top",
            wrap=True,
        )
        y -= 0.07

        descripcion = (ficha or {}).get("descripcion")
        if descripcion:
            _section_title(fig, 0.055, y, "Biografía (TheSportsDB, en inglés)")
            y -= 0.03
            texto = descripcion[:700] + ("…" if len(descripcion) > 700 else "")
            fig.text(0.055, y, texto, fontsize=8.5, color=_TEXT, va="top", wrap=True, ha="left")
            # ~95 caracteres por línea envuelta a este ancho y tamaño; estimación
            # generosa para dejar sitio de sobra sin reservar el máximo siempre.
            lineas = -(-len(texto) // 95)  # división entera hacia arriba
            y -= lineas * 0.0145 + 0.025
        # sin biografía, lo de abajo sube directamente: nada de hueco reservado
        # para una sección que la fuente no tenía.

        if temporadas:
            _section_title(fig, 0.055, y, "Estadísticas de temporada (Sportmonks)")
            y -= 0.03
            fig.text(
                0.055,
                y,
                "Totales por club y temporada. Apariciones = partidos jugados (titular o suplente); "
                "titularidades = partidos de inicio; goles encajados y porterías a cero solo aplican "
                "a porteros.",
                fontsize=7,
                color=_MUTED,
                va="top",
                wrap=True,
            )
            y -= 0.05
            from . import sportmonks  # import perezoso: report no depende de sportmonks en general

            cols = [c for c in sportmonks.STAT_MAP.values() if any(c in t for t in temporadas)]
            header = ["Temporada", *[sportmonks.STAT_LABELS[c] for c in cols]]
            filas = sorted(temporadas, key=lambda t: str(t.get("season_name", "")), reverse=True)
            table_data = [header]
            for t in filas[:10]:
                fila = [str(t.get("season_name", ""))]
                for c in cols:
                    v = t.get(c)
                    fila.append(f"{v:.0f}" if isinstance(v, (int, float)) else "—")
                table_data.append(fila)

            alto_tabla = min(0.045 * len(table_data), y - 0.08)
            ax = fig.add_axes((0.055, y - alto_tabla, 0.89, alto_tabla))
            ax.axis("off")
            tbl = ax.table(cellText=table_data, loc="center", cellLoc="center")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.auto_set_column_width(col=list(range(len(header))))
            tbl.scale(1, 1.6)
            for (row, _col), cell in tbl.get_celld().items():
                cell.set_edgecolor(_GRID)
                if row == 0:
                    cell.set_facecolor(_PANEL)
                    cell.set_text_props(fontweight="bold", color=_ACCENT)
                else:
                    cell.set_facecolor(_BG)
                    cell.set_text_props(color=_TEXT)
            y -= alto_tabla + 0.03
        else:
            fig.text(
                0.055,
                y,
                "Sin estadísticas de temporada disponibles (falta token de Sportmonks, o el "
                "jugador no está en su cobertura).",
                fontsize=9,
                color=_MUTED,
                va="top",
            )
            y -= 0.03

        if traspasos:
            _section_title(fig, 0.055, y, "Traspasos reales (Sportmonks)")
            y -= 0.026
            filas_traspasos = sorted(traspasos, key=lambda t: t.get("fecha") or "", reverse=True)
            for t in filas_traspasos[:3]:
                importe = t.get("importe")
                importe_txt = f"{importe:,.0f} €".replace(",", ".") if importe else "importe no público"
                origen = t.get("origen") or "?"
                destino = t.get("destino") or "?"
                fig.text(
                    0.055,
                    y,
                    _truncate(f"{t.get('fecha', '?')} — {origen} → {destino} · {importe_txt}", 80),
                    fontsize=8,
                    color=_TEXT,
                    va="top",
                )
                y -= 0.017
            y -= 0.015

        fig.text(
            0.055,
            min(y, 0.03),
            "FUTBOL-ANALYTICS · FUENTES: THESPORTSDB, SPORTMONKS",
            fontsize=5.5,
            color=_MUTED,
        )

        out = io.BytesIO()
        fig.savefig(out, format="pdf", facecolor=fig.get_facecolor())
        plt.close(fig)
        return out.getvalue()
