"""Informe-CV de una página: radar, mapas, similares y destinos en un PDF A4.

Compone las visualizaciones existentes (radar de percentiles, mapa de
calor, pases y tiros) con el top de perfiles similares y los mejores
destinos del motor de encaje. Siempre en tema claro: es un documento
para imprimir o adjuntar.
"""

from __future__ import annotations

import gc
import io

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from PIL import Image

from . import fit, narrative, photos, similarity, viz

WHITE = "#ffffff"


def _fig_png(fig, dpi: int = 110) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _embed_photo(fig, url: str | None, pos: tuple[float, float, float, float]) -> bool:
    """Incrusta la foto del jugador si hay URL y se puede descargar; si no, no dibuja nada.

    Un PDF sin foto sigue siendo válido: es mejor un hueco en blanco que
    reventar el informe por una foto caída o un formato que PIL no reconozca.
    Devuelve si se dibujó, para que el llamante decida si reservar sitio
    para ella o cerrar el hueco.
    """
    if not url:
        return False
    data = photos.fetch_bytes(url)
    if not data:
        return False
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return False
    ax = fig.add_axes(pos)
    # lanczos suaviza el escalado de fotos pequeñas (avatares de TheSportsDB/
    # Sportmonks); no añade detalle que no había, pero evita el aspecto
    # "pixelado" del muestreo por vecino más cercano que usa matplotlib por defecto.
    ax.imshow(img, interpolation="lanczos")
    ax.axis("off")
    return True


def _header_band(fig, title: str, height: float = 0.06) -> None:
    """Franja de color a todo lo ancho con el nombre en blanco, como cabecera del documento."""
    ax = fig.add_axes((0, 1 - height, 1, height))
    ax.set_facecolor(viz.BLUE)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(
        0.045, 0.5, title, fontsize=21, fontweight="bold", color=WHITE, va="center", transform=ax.transAxes
    )


def _section_heading(fig, x: float, y: float, text: str) -> None:
    """Título de sección con una marca de color a la izquierda, no solo negrita suelta."""
    fig.add_artist(Rectangle((x, y - 0.009), 0.008, 0.015, transform=fig.transFigure, color=viz.BLUE, lw=0))
    fig.text(x + 0.016, y, text, fontsize=11, fontweight="bold", color=viz.INK, va="top")


def _stat_tiles(fig, y_top: float, height: float, stats: list[tuple[str, str, float]]) -> None:
    """Fila de tarjetas con tinte de color: valor grande + etiqueta + percentil.

    `stats` es una lista de (etiqueta, valor_formateado, percentil). Sustituye
    la antigua línea de texto plano "npxG/90 0.36 (p88)  xA/90 ..." por algo
    con estructura visual, no todo apretado en una frase.
    """
    tile_fill = "#eaf1fc"  # tinte claro de viz.BLUE, consistente con la cabecera de tabla
    n = len(stats)
    gap = 0.015
    width = (0.92 - gap * (n - 1)) / n
    for i, (label, valor, pct) in enumerate(stats):
        x = 0.06 + i * (width + gap)
        ax = fig.add_axes((x, y_top - height, width, height))
        ax.set_facecolor(tile_fill)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(0.5, 0.68, valor, fontsize=15, fontweight="bold", color=viz.BLUE, ha="center", va="center")
        ax.text(
            0.5,
            0.28,
            f"{label} · p{pct:.0f}",
            fontsize=7.5,
            color=viz.INK_2,
            ha="center",
            va="center",
        )


def _truncate(text: str, maxlen: int = 56) -> str:
    """Corta una línea antes de que invada la columna vecina.

    Nombres reales (p. ej. "Lionel Andrés Messi Cuccittini... Right Center
    Forward") son mucho más largos que los de prueba y sin esto se salen
    de su columna a dos columnas por página.
    """
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def player_report_pdf(
    table: pd.DataFrame,
    events: pd.DataFrame,
    player: str,
    comp_label: str,
    display: str | None = None,
    photo_url: str | None = None,
) -> bytes:
    """PDF de una página con el informe completo del jugador."""
    viz.use_theme("light")
    prow = table[table["player"] == player].iloc[0]
    apodo = prow.get("nickname")
    display = display or (apodo if isinstance(apodo, str) and apodo else player)

    rol = prow.get("role")
    pool = str(rol).lower() + "s" if prow.get("pct_basis") == "role" and isinstance(rol, str) else None
    pool_desc = pool or str(prow["position_group"])

    paneles = [
        _fig_png(viz.radar_chart(prow, comp_label, display, pool)),
        _fig_png(viz.shot_map(events, player, comp_label, display)),
        _fig_png(viz.touch_heatmap(events, player, comp_label, display)),
        _fig_png(viz.pass_map(events, player, comp_label, display)),
    ]

    sims = similarity.similar_players(table, player).head(5)
    destinos = fit.teams_for_player(table, events, player)
    destinos = destinos[~destinos["propio"]].head(5)

    fig = plt.figure(figsize=(8.27, 11.69))  # A4 vertical
    fig.set_facecolor(viz.SURFACE)

    subtitulo = " · ".join(
        str(v)
        for v in (
            prow["team"],
            prow["primary_position"],
            rol if isinstance(rol, str) else None,
            f"{prow['minutes']:.0f} min",
            comp_label,
        )
        if v
    )
    _header_band(fig, display, height=0.035)
    # aspecto casi cuadrado (no la franja ancha de antes): menos estiramiento
    # al escalar avatares pequeños, que es lo que más se nota como "borroso"
    foto_ok = _embed_photo(fig, photo_url, (0.06, 0.865, 0.14, 0.095))
    x_text = 0.23 if foto_ok else 0.06

    fig.text(x_text, 0.95, subtitulo, fontsize=10, color=viz.INK_2, va="top")
    resumen_texto = narrative.player_summary(prow, pool_desc, sims)
    if resumen_texto:
        fig.text(x_text, 0.923, resumen_texto, fontsize=8.5, color=viz.INK_2, va="top", wrap=True)

    tiles = [
        ("npxG/90", f"{prow['npxg_p90']:.2f}", prow["npxg_p90_pct"]),
        ("xA/90", f"{prow['xa_p90']:.2f}", prow["xa_p90_pct"]),
        ("Pases prog./90", f"{prow['prog_passes_p90']:.1f}", prow["prog_passes_p90_pct"]),
        ("Presiones/90", f"{prow['pressures_p90']:.1f}", prow["pressures_p90_pct"]),
    ]
    # la narrativa ahora ocupa varias líneas (explica cada métrica, no solo la
    # nombra): las tarjetas y los paneles bajan para dejarle sitio
    _stat_tiles(fig, y_top=0.815, height=0.05, stats=tiles)

    posiciones = [  # (izquierda, abajo, ancho, alto) en fracción de página
        (0.035, 0.46, 0.46, 0.3),
        (0.515, 0.46, 0.46, 0.3),
        (0.035, 0.13, 0.46, 0.3),
        (0.515, 0.13, 0.46, 0.3),
    ]
    for buf, pos in zip(paneles, posiciones):
        ax = fig.add_axes(pos)
        ax.imshow(mpimg.imread(buf))
        ax.axis("off")

    y0 = 0.115
    _section_heading(fig, 0.06, y0, "Perfiles similares")
    for i, (_, s) in enumerate(sims.iterrows()):
        fig.text(
            0.06,
            y0 - 0.021 - 0.016 * i,
            _truncate(f"{s['similarity']:.3f}   {s['player']}  ({s['team']}, {s['primary_position']})"),
            fontsize=8.5,
            color=viz.INK_2,
            va="top",
        )

    _section_heading(fig, 0.54, y0, "Mejores destinos (encaje)")
    for i, (_, d) in enumerate(destinos.iterrows()):
        fig.text(
            0.54,
            y0 - 0.021 - 0.016 * i,
            _truncate(
                f"{d['encaje']:.0f}   {d['team']}  (estilo {d['estilo']:+.2f}, mejora {d['mejora_puesto']:+.0f})"
            ),
            fontsize=8.5,
            color=viz.INK_2,
            va="top",
        )

    fig.text(
        0.06,
        0.014,
        "Generado con futbol-analytics · Datos: StatsBomb open data (uso no comercial)",
        fontsize=7,
        color=viz.MUTED,
    )

    out = io.BytesIO()
    fig.savefig(out, format="pdf", facecolor=fig.get_facecolor())
    plt.close(fig)
    data = out.getvalue()
    # este informe es el que más memoria mueve (cuatro paneles a la vez
    # sobre los eventos de toda la competición); liberar cuanto antes en
    # vez de esperar al ciclo normal del GC importa en un contenedor con
    # RAM ajustada (Streamlit Community Cloud, ~1 GB)
    gc.collect()
    return data


def ficha_report_pdf(ficha: dict | None, ficha_sm: dict | None, query: str) -> bytes:
    """PDF de una página para un jugador fuera de los open data cargados.

    Sin eventos con coordenadas no hay radar, mapas ni encaje — pero la
    biografía de TheSportsDB y las estadísticas de temporada de Sportmonks
    (si hay token) ya bastan para una ficha presentable. `ficha` y
    `ficha_sm` pueden venir ambas a None si ningún servicio tuvo datos;
    el PDF se genera igual, dejándolo dicho. El layout es secuencial (cada
    bloque calcula dónde empieza el siguiente): una sección ausente (sin
    biografía, por ejemplo) no deja un hueco en blanco reservado para ella.
    """
    viz.use_theme("light")
    candidatos_nombre = [
        n
        for n in ((ficha or {}).get("nombre"), (ficha_sm or {}).get("nombre"), query)
        if isinstance(n, str) and n.strip()
    ]
    # el nombre más largo suele ser el más completo (p. ej. la búsqueda del
    # usuario "Franculino Djú" frente a un display_name corto de la API)
    nombre = max(candidatos_nombre, key=len) if candidatos_nombre else query
    foto_url = (ficha or {}).get("foto") or (ficha_sm or {}).get("foto")

    fig = plt.figure(figsize=(8.27, 11.69))  # A4 vertical
    fig.set_facecolor(viz.SURFACE)

    _header_band(fig, nombre, height=0.075)
    foto_ok = _embed_photo(fig, foto_url, (0.06, 0.815, 0.16, 0.1))
    x_text = 0.26 if foto_ok else 0.06

    y = 0.895
    if ficha:
        subtitulo = " · ".join(
            str(v) for v in (ficha.get("equipo"), ficha.get("posicion"), ficha.get("nacionalidad")) if v
        )
        if subtitulo:
            fig.text(x_text, y, subtitulo, fontsize=12, color=viz.INK_2, va="top")
            y -= 0.03
        detalles = " · ".join(
            str(v) for v in (ficha.get("nacimiento"), ficha.get("lugar_nacimiento"), ficha.get("altura")) if v
        )
        if detalles:
            fig.text(x_text, y, detalles, fontsize=10, color=viz.MUTED, va="top")
            y -= 0.03

    y = min(y, 0.8) - 0.02  # bajo la foto y el texto de cabecera, sea cual sea su alto real
    fig.text(
        0.06,
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
        _section_heading(fig, 0.06, y, "Biografía (TheSportsDB, en inglés)")
        y -= 0.03
        texto = descripcion[:700] + ("…" if len(descripcion) > 700 else "")
        fig.text(0.06, y, texto, fontsize=8.5, color=viz.INK_2, va="top", wrap=True, ha="left")
        # ~95 caracteres por línea envuelta a este ancho y tamaño; estimación
        # generosa para dejar sitio de sobra sin reservar el máximo siempre.
        lineas = -(-len(texto) // 95)  # división entera hacia arriba
        y -= lineas * 0.0145 + 0.025
    # sin biografía, lo de abajo sube directamente: nada de hueco reservado
    # para una sección que la fuente no tenía.

    temporadas = (ficha_sm or {}).get("temporadas") or []
    if temporadas:
        _section_heading(fig, 0.06, y, "Estadísticas de temporada (Sportmonks)")
        y -= 0.028
        fig.text(
            0.06,
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
        ax = fig.add_axes((0.06, y - alto_tabla, 0.88, alto_tabla))
        ax.axis("off")
        tbl = ax.table(cellText=table_data, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.auto_set_column_width(col=list(range(len(header))))
        tbl.scale(1, 1.6)
        header_fill = "#e4eefb"  # tinte claro de viz.BLUE: cabecera de tabla distinguible
        for (row, _col), cell in tbl.get_celld().items():
            cell.set_edgecolor(viz.GRID)
            if row == 0:
                cell.set_facecolor(header_fill)
                cell.set_text_props(fontweight="bold", color=viz.BLUE)
            else:
                cell.set_facecolor(viz.SURFACE)
                cell.set_text_props(color=viz.INK_2)
    else:
        fig.text(
            0.06,
            y,
            "Sin estadísticas de temporada disponibles (falta token de Sportmonks, o el "
            "jugador no está en su cobertura).",
            fontsize=9,
            color=viz.MUTED,
            va="top",
        )

    fig.text(
        0.06,
        0.03,
        "Generado con futbol-analytics · Fuentes: TheSportsDB, Sportmonks",
        fontsize=7,
        color=viz.MUTED,
    )

    out = io.BytesIO()
    fig.savefig(out, format="pdf", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out.getvalue()
