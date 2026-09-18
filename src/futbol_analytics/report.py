"""Informe-CV del jugador: foto de cabecera, radar, mapas reales, similares y destinos.

Plantilla oscura con tipografía Inter (SIL OFL, empaquetada en
assets/fonts/), foto a banda completa en la cabecera y paneles de mapas
reales generados con matplotlib + mplsoccer — nunca imágenes simuladas.
Todo el texto explicativo viene de narrative.py (reglas deterministas sobre
datos ya calculados), nunca inventado; el "percentil medio" del medidor es
la media real de los mismos percentiles que dibuja el radar, no una
puntuación arbitraria.

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
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Wedge
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
_FONT_CONTEXT = {"font.family": "sans-serif", "font.sans-serif": ["Inter", "DejaVu Sans"]}

# npxG/xA son tasas pequeñas (casi siempre < 1): con un decimal se verían
# como "0.0" para casi cualquier jugador. El resto de métricas per-90 del
# radar son recuentos (pases, presiones...) donde un decimal ya distingue.
_TWO_DECIMAL_METRICS = {"npxg_p90", "xa_p90"}


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


def _photo_box(
    img: Image.Image | None, aspect_w: float, aspect_h: float, fade_frac: float = 0.55
) -> Image.Image:
    """Recorta la foto al aspect ratio de la caja (cover-fit, sin deformar) y funde
    su borde izquierdo con el fondo oscuro (scrim), para que el nombre pueda
    montarse encima y siga siendo legible sin depender de lo clara u oscura
    que sea la foto real.

    `aspect_w`/`aspect_h` son solo la proporción de la caja destino (en
    pulgadas de figura, p. ej. `photo_w_frac * PAGE_SIZE[0]`): aquí solo se
    recorta, nunca se redimensiona con PIL — matplotlib ya reescala con
    `interpolation="lanczos"` al dibujar (mismo patrón que el resto del
    informe para fotos pequeñas), así que forzar aquí un tamaño de píxeles
    fijo sería un resize redundante.

    Sin foto, un informe sigue siendo válido: rectángulo plano del color de
    panel en vez de un hueco vacío que desentone del resto de la cabecera.
    """
    bg = _hex_to_rgb(viz.PANEL)
    box_ratio = aspect_w / aspect_h
    if img is not None:
        img = img.convert("RGB")
        src_ratio = img.width / img.height
        if src_ratio > box_ratio:
            new_w = int(img.height * box_ratio)
            x0 = (img.width - new_w) // 2
            img = img.crop((x0, 0, x0 + new_w, img.height))
        else:
            new_h = int(img.width / box_ratio)
            y0 = (img.height - new_h) // 2
            img = img.crop((0, y0, img.width, y0 + new_h))
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
    fig.text(x, y, text.upper(), fontsize=8, fontweight="bold", color=viz.MUTED, va="top")
    fig.add_artist(
        plt.Line2D([x, x + width], [y - 0.006, y - 0.006], transform=fig.transFigure, color=viz.GRID, lw=0.8)
    )


def _hero_band(
    fig,
    name: str,
    subtitle: str,
    info_items: list[tuple[str, str]],
    photo_url: str | None,
    crest_url: str | None,
    hero_h: float,
    photo_w_frac: float = 0.62,
    item_gap: float = 0.19,
) -> float:
    """Cabecera: foto a banda completa (funde a la izquierda), nombre montado
    encima, fila de datos y escudo del equipo. Devuelve la y donde puede
    empezar el resto de la página (justo bajo el borde inferior de la foto).
    """
    photo_img = _photo_box(_fetch_image(photo_url), photo_w_frac * PAGE_SIZE[0], hero_h * PAGE_SIZE[1])
    ax_photo = fig.add_axes((1 - photo_w_frac, 1 - hero_h, photo_w_frac, hero_h))
    ax_photo.imshow(photo_img, interpolation="lanczos")
    ax_photo.axis("off")

    fig.text(
        0.055,
        0.955,
        "INFORME DE JUGADOR · FUTBOL-ANALYTICS",
        fontsize=7.5,
        fontweight="bold",
        color=viz.BLUE,
        va="top",
    )
    fig.text(0.05, 0.90, _truncate(name, 24), fontsize=34, fontweight="bold", color=viz.INK, va="top")
    if subtitle:
        fig.text(0.055, 0.842, subtitle.upper(), fontsize=9.5, fontweight="bold", color=viz.BLUE, va="top")

    info_y = 0.80
    crest_size = 0.022
    crest_pos = (0.055, info_y - 0.014 - 0.014, crest_size, crest_size * PAGE_SIZE[0] / PAGE_SIZE[1])
    crest_drawn = _embed_image(fig, crest_url, crest_pos, min_dpi=90.0)

    for i, (label, value) in enumerate(info_items):
        x = 0.055 + i * item_gap
        fig.text(x, info_y, label.upper(), fontsize=6, fontweight="bold", color=viz.MUTED, va="top")
        text_x = x + 0.024 if (i == 0 and crest_drawn) else x
        fig.text(
            text_x,
            info_y - 0.014,
            _truncate(value, 15),
            fontsize=9,
            fontweight="bold",
            color=viz.INK,
            va="top",
        )

    return 1 - hero_h - 0.035


def _mini_pitch(figsize: tuple[float, float] = (3.5, 2.5)):
    pitch = Pitch(pitch_type="statsbomb", pitch_color=viz.PANEL, line_color=viz.BASELINE, linewidth=1)
    fig, ax = pitch.draw(figsize=figsize)
    fig.set_facecolor(viz.PANEL)
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
        pitch.heatmap(stats, ax=ax, cmap=viz.SEQ_BLUE, edgecolors="none", zorder=0)
    return fig


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
    for df, color, alpha, lw, z in ((others, viz.MUTED, 0.35, 1.2, 1), (key, viz.ORANGE, 0.85, 2.2, 2)):
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
    handles = [
        Line2D([], [], color=viz.ORANGE, lw=2.5, label=f"Clave/asistencia ({len(key)})"),
        Line2D([], [], color=viz.MUTED, lw=2.5, label=f"Resto ({len(others)})"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=6, frameon=False, labelcolor=viz.INK_2)
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
        (prog_passes, "pass_end_location", viz.BLUE, 0.6),
        (prog_carries, "carry_end_location", viz.ORANGE, 0.75),
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
    handles = [
        Line2D([], [], color=viz.BLUE, lw=2.5, label=f"Pases prog. ({len(prog_passes)})"),
        Line2D([], [], color=viz.ORANGE, lw=2.5, label=f"Conducciones prog. ({len(prog_carries)})"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=6, frameon=False, labelcolor=viz.INK_2)
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
        ("Presión", ev["type"] == "Pressure", viz.BLUE),
        ("Entrada", duel_tackle, viz.ORANGE),
        ("Intercepción", ev["type"] == "Interception", viz.AQUA),
        ("Bloqueo/despeje", ev["type"].isin(["Block", "Clearance"]), viz.MUTED),
    ]
    pitch, fig, ax = _mini_pitch()
    handles = []
    for label, mask, color in kinds:
        sub = ev[mask.fillna(False)]
        if sub.empty:
            continue
        x = sub["location"].str[0].astype(float)
        y = sub["location"].str[1].astype(float)
        pitch.scatter(x, y, s=45, ax=ax, facecolor=color, edgecolor=viz.PANEL, linewidth=0.6, zorder=2)
        handles.append(
            Line2D([], [], marker="o", ls="", mfc=color, mec="none", ms=7, label=f"{label} ({len(sub)})")
        )
    if handles:
        ax.legend(handles=handles, loc="lower left", fontsize=6, frameon=False, labelcolor=viz.INK_2)
    return fig


def _panel_shot_map(events: pd.DataFrame, player: str):
    ev = _report_player_events(events, player)
    shots = ev[(ev["type"] == "Shot") & (ev.get("shot_type") != "Penalty")].copy()
    goals = shots[shots["shot_outcome"] == "Goal"]
    misses = shots[shots["shot_outcome"] != "Goal"]

    pitch = VerticalPitch(
        pitch_type="statsbomb", half=True, pitch_color=viz.PANEL, line_color=viz.BASELINE, linewidth=1
    )
    fig, ax = pitch.draw(figsize=(3.1, 2.5))
    fig.set_facecolor(viz.PANEL)

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

    _plot(misses, facecolor="none", edgecolor=viz.MUTED, linewidth=1.1)
    _plot(goals, facecolor=viz.BLUE, edgecolor=viz.PANEL, linewidth=1, alpha=0.9)

    handles = [
        Line2D([], [], marker="o", ls="", mfc=viz.BLUE, mec=viz.PANEL, ms=7, label=f"Gol ({len(goals)})"),
        Line2D([], [], marker="o", ls="", mfc="none", mec=viz.MUTED, ms=7, label=f"Sin gol ({len(misses)})"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=6, frameon=False, labelcolor=viz.INK_2)
    return fig


def player_report_pdf(
    table: pd.DataFrame,
    events: pd.DataFrame,
    player: str,
    comp_label: str,
    display: str | None = None,
    photo_url: str | None = None,
    crest_url: str | None = None,
) -> bytes:
    """PDF de dos páginas con el informe completo del jugador."""
    viz.use_theme("dark")
    with plt.rc_context(_FONT_CONTEXT):
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

        fig1 = plt.figure(figsize=PAGE_SIZE)
        fig1.set_facecolor(viz.SURFACE)

        hero_h = 0.27
        y0 = _hero_band(
            fig1,
            display,
            posicion,
            [
                ("Equipo", str(prow["team"])),
                ("Competición", comp_label),
                ("Minutos", f"{prow['minutes']:.0f}′"),
                ("Comparado con", pool_desc),
            ],
            photo_url,
            crest_url,
            hero_h=hero_h,
        )

        # --- Perfil (izquierda) + Puntos fuertes / Por mejorar (derecha) ---
        _section_title(fig1, 0.055, y0, "Perfil", width=0.46)
        if resumen:
            for i, linea in enumerate(textwrap.wrap(resumen, width=50)):
                fig1.text(0.055, y0 - 0.020 - i * 0.0155, linea, fontsize=8, color=viz.INK_2, va="top")

        def _rasgos_col(x: float, titulo: str, y_start: float, rasgos: list[tuple[str, str]]) -> float:
            _section_title(fig1, x, y_start, titulo, width=0.34)
            yy = y_start
            for t, d in rasgos[:2]:
                yy -= 0.020
                fig1.text(x, yy, t, fontsize=8, fontweight="bold", color=viz.INK, va="top")
                if d:
                    yy -= 0.0125
                    fig1.text(x, yy, _truncate(d, 46), fontsize=6.5, color=viz.MUTED, va="top")
                yy -= 0.006
            return yy

        x_right = 0.58
        yy = _rasgos_col(x_right, "Puntos fuertes", y0, fortalezas)
        yy -= 0.016
        _rasgos_col(x_right, "Por mejorar", yy, debilidades)

        y1 = y0 - 0.185

        # --- Datos clave: mismos percentiles que dibuja el radar ---
        _section_title(fig1, 0.055, y1, "Datos clave (per-90 y percentil vs. su rol)")
        key_metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])[:6]
        row_h = 0.0205
        for i, (col, label) in enumerate(key_metrics):
            yy_row = y1 - 0.026 - i * row_h
            raw_col = col[:-4] if col.endswith("_pct") else col
            valor = _fmt_metric_value(prow, raw_col)
            pct = float(prow[col]) if pd.notna(prow.get(col)) else 0.0
            fig1.text(0.055, yy_row, label.replace("\n", " "), fontsize=7.5, color=viz.INK_2, va="top")
            fig1.text(0.32, yy_row, valor, fontsize=7.5, fontweight="bold", color=viz.INK, va="top")
            ax_bar = fig1.add_axes((0.42, yy_row - row_h * 0.55, 0.42, row_h * 0.32))
            ax_bar.set_xlim(0, 100)
            ax_bar.set_ylim(0, 1)
            ax_bar.axis("off")
            ax_bar.barh([0.5], [100], height=1, color=viz.GRID)
            ax_bar.barh([0.5], [pct], height=1, color=viz.BLUE)
            fig1.text(0.87, yy_row, f"p{pct:.0f}", fontsize=7, color=viz.MUTED, va="top")

        y2 = y1 - 0.026 - len(key_metrics) * row_h - 0.020

        # --- Radar + percentil medio (media real de los mismos percentiles del radar) ---
        _section_title(fig1, 0.055, y2, "Radar y percentil medio")
        full_metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])
        valores_pct = [float(prow[c]) for c, _ in full_metrics if pd.notna(prow.get(c))]
        avg_percentile = float(np.mean(valores_pct)) if valores_pct else 0.0
        radar_fig = viz.radar_chart(prow, comp_label, display, pool, header=False)
        radar_h = 0.13
        ax_radar = fig1.add_axes((0.05, y2 - 0.018 - radar_h, 0.50, radar_h))
        ax_radar.imshow(mpimg.imread(_panel_png(radar_fig)))
        ax_radar.axis("off")

        gauge_cx, gauge_cy, gauge_r = 0.73, y2 - 0.018 - radar_h / 2, 0.042
        ax_gauge = fig1.add_axes((0, 0, 1, 1))
        ax_gauge.set_xlim(0, 1)
        ax_gauge.set_ylim(0, 1)
        ax_gauge.axis("off")
        ax_gauge.set_zorder(5)
        ax_gauge.add_patch(Wedge((gauge_cx, gauge_cy), gauge_r, 0, 360, width=0.013, facecolor=viz.GRID))
        ax_gauge.add_patch(
            Wedge(
                (gauge_cx, gauge_cy),
                gauge_r,
                90,
                90 + 360 * avg_percentile / 100,
                width=0.013,
                facecolor=viz.BLUE,
            )
        )
        ax_gauge.text(
            gauge_cx,
            gauge_cy,
            f"{avg_percentile:.0f}",
            fontsize=14,
            fontweight="bold",
            color=viz.INK,
            ha="center",
            va="center",
        )
        ax_gauge.text(
            gauge_cx,
            gauge_cy - gauge_r - 0.018,
            "PERCENTIL MEDIO",
            fontsize=5.5,
            fontweight="bold",
            color=viz.MUTED,
            ha="center",
            va="top",
        )

        y3 = y2 - 0.018 - radar_h - 0.022

        # --- Mapas (5 paneles reales) ---
        _section_title(fig1, 0.055, y3, "Mapas")
        panels = [
            ("Mapa de calor", _panel_heatmap(events, player)),
            ("Passing map", _panel_passing_map(events, player)),
            ("Acciones progresivas", _panel_progressive_map(events, player)),
            ("Acciones defensivas", _panel_defensive_map(events, player)),
            ("Mapa de tiros", _panel_shot_map(events, player)),
        ]
        n = len(panels)
        gap = 0.013
        panel_w = (0.89 - gap * (n - 1)) / n
        panel_h = 0.078
        for i, (label, pf) in enumerate(panels):
            x = 0.055 + i * (panel_w + gap)
            fig1.text(x, y3 - 0.020, label.upper(), fontsize=5, fontweight="bold", color=viz.MUTED, va="top")
            ax_bg = fig1.add_axes((x, y3 - 0.030 - panel_h, panel_w, panel_h))
            ax_bg.add_patch(
                FancyBboxPatch(
                    (0, 0),
                    1,
                    1,
                    boxstyle="round,pad=0,rounding_size=0.05",
                    facecolor=viz.PANEL,
                    edgecolor="none",
                    transform=ax_bg.transAxes,
                )
            )
            ax_bg.axis("off")
            ax_img = fig1.add_axes((x + 0.005, y3 - 0.030 - panel_h + 0.005, panel_w - 0.01, panel_h - 0.01))
            ax_img.imshow(mpimg.imread(_panel_png(pf)))
            ax_img.axis("off")

        fig1.text(
            0.055,
            0.02,
            "FUTBOL-ANALYTICS · DATOS: STATSBOMB OPEN DATA · NADA INVENTADO, TODO VERIFICABLE",
            fontsize=5.5,
            color=viz.MUTED,
        )

        # --- Página 2: perfiles similares y mejores destinos (motor de encaje) ---
        # 4, no 5: deja sitio a la nota de que "parecido" es de estilo, no de nivel
        sims = similarity.similar_players(table, player).head(4)
        destinos = fit.teams_for_player(table, events, player)
        destinos = destinos[~destinos["propio"]].head(5)

        fig2 = plt.figure(figsize=PAGE_SIZE)
        fig2.set_facecolor(viz.SURFACE)
        fig2.text(
            0.055,
            0.955,
            "INFORME DE JUGADOR · FUTBOL-ANALYTICS",
            fontsize=7.5,
            fontweight="bold",
            color=viz.BLUE,
            va="top",
        )
        fig2.text(
            0.055, 0.925, _truncate(display, 40), fontsize=16, fontweight="bold", color=viz.INK, va="top"
        )

        y_top = 0.86
        _section_title(fig2, 0.055, y_top, "Perfiles similares", width=0.42)
        fig2.text(
            0.055,
            y_top - 0.02,
            "estilo parecido, no necesariamente el mismo nivel",
            fontsize=6.5,
            color=viz.MUTED,
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
                color=viz.INK_2,
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
                color=viz.INK_2,
                va="top",
            )

        fig2.text(
            0.055,
            0.02,
            "FUTBOL-ANALYTICS · DATOS: STATSBOMB OPEN DATA · NADA INVENTADO, TODO VERIFICABLE",
            fontsize=5.5,
            color=viz.MUTED,
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
    viz.use_theme("dark")
    with plt.rc_context(_FONT_CONTEXT):
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
        fig.set_facecolor(viz.SURFACE)

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
        y = _hero_band(fig, nombre, "", info_items, foto_url, crest_url, hero_h=hero_h)

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
            fig.text(0.055, y, detalles, fontsize=8.5, color=viz.MUTED, va="top")
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
                fig.text(0.055, y_t, titulo, fontsize=8.5, color=viz.INK_2, va="top")
                if definicion:
                    fig.text(
                        0.055, y_t - 0.013, _truncate(definicion, 68), fontsize=6.5, color=viz.MUTED, va="top"
                    )
            if a_vigilar:
                _section_title(fig, 0.54, y_top, "A vigilar", width=0.4)
                for i, (titulo, definicion) in enumerate(a_vigilar):
                    y_t = y_top - 0.024 - i * 0.033
                    fig.text(0.54, y_t, titulo, fontsize=8.5, color=viz.INK_2, va="top")
                    if definicion:
                        fig.text(
                            0.54,
                            y_t - 0.013,
                            _truncate(definicion, 68),
                            fontsize=6.5,
                            color=viz.MUTED,
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
            color=viz.MUTED,
            va="top",
            wrap=True,
        )
        y -= 0.07

        descripcion = (ficha or {}).get("descripcion")
        if descripcion:
            _section_title(fig, 0.055, y, "Biografía (TheSportsDB, en inglés)")
            y -= 0.03
            texto = descripcion[:700] + ("…" if len(descripcion) > 700 else "")
            fig.text(0.055, y, texto, fontsize=8.5, color=viz.INK_2, va="top", wrap=True, ha="left")
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
                color=viz.MUTED,
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
                cell.set_edgecolor(viz.GRID)
                if row == 0:
                    cell.set_facecolor(viz.PANEL)
                    cell.set_text_props(fontweight="bold", color=viz.BLUE)
                else:
                    cell.set_facecolor(viz.SURFACE)
                    cell.set_text_props(color=viz.INK_2)
            y -= alto_tabla + 0.03
        else:
            fig.text(
                0.055,
                y,
                "Sin estadísticas de temporada disponibles (falta token de Sportmonks, o el "
                "jugador no está en su cobertura).",
                fontsize=9,
                color=viz.MUTED,
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
                    color=viz.INK_2,
                    va="top",
                )
                y -= 0.017
            y -= 0.015

        fig.text(
            0.055,
            min(y, 0.03),
            "FUTBOL-ANALYTICS · FUENTES: THESPORTSDB, SPORTMONKS",
            fontsize=5.5,
            color=viz.MUTED,
        )

        out = io.BytesIO()
        fig.savefig(out, format="pdf", facecolor=fig.get_facecolor())
        plt.close(fig)
        return out.getvalue()
