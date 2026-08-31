"""Informe-CV de una página: radar, mapas, similares y destinos en un PDF A4.

Compone las visualizaciones existentes (radar de percentiles, mapa de
calor, pases y tiros) con el top de perfiles similares y los mejores
destinos del motor de encaje. Siempre en tema claro: es un documento
para imprimir o adjuntar.
"""

from __future__ import annotations

import io

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

from . import fit, photos, similarity, viz


def _fig_png(fig, dpi: int = 150) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _embed_photo(fig, url: str | None, pos: tuple[float, float, float, float]) -> None:
    """Incrusta la foto del jugador si hay URL y se puede descargar; si no, no dibuja nada.

    Un PDF sin foto sigue siendo válido: es mejor un hueco en blanco que
    reventar el informe por una foto caída o un formato que PIL no reconozca.
    """
    if not url:
        return
    data = photos.fetch_bytes(url)
    if not data:
        return
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return
    ax = fig.add_axes(pos)
    ax.imshow(img)
    ax.axis("off")


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
    _embed_photo(fig, photo_url, (0.06, 0.905, 0.15, 0.07))

    fig.text(0.24, 0.978, display, fontsize=20, fontweight="bold", color=viz.INK, va="top")
    fig.text(0.24, 0.95, subtitulo, fontsize=10, color=viz.INK_2, va="top")
    resumen = (
        f"npxG/90 {prow['npxg_p90']:.2f} (p{prow['npxg_p90_pct']:.0f})    "
        f"xA/90 {prow['xa_p90']:.2f} (p{prow['xa_p90_pct']:.0f})    "
        f"Pases prog./90 {prow['prog_passes_p90']:.1f} (p{prow['prog_passes_p90_pct']:.0f})    "
        f"Presiones/90 {prow['pressures_p90']:.1f} (p{prow['pressures_p90_pct']:.0f})"
    )
    fig.text(0.24, 0.931, resumen, fontsize=9, color=viz.INK, va="top")
    fig.text(
        0.24,
        0.915,
        "npxG = goles esperados sin penaltis · xA = asistencia esperada del pase previo al tiro · "
        "pases prog. = avanzan ≥25% hacia la portería rival · presiones = acciones para forzar la "
        "pérdida rival. Percentil entre paréntesis, frente a otros " + pool_desc + ".",
        fontsize=6.5,
        color=viz.MUTED,
        va="top",
        wrap=True,
    )

    posiciones = [  # (izquierda, abajo, ancho, alto) en fracción de página
        (0.035, 0.545, 0.46, 0.355),
        (0.515, 0.545, 0.46, 0.355),
        (0.035, 0.175, 0.46, 0.35),
        (0.515, 0.175, 0.46, 0.35),
    ]
    for buf, pos in zip(paneles, posiciones):
        ax = fig.add_axes(pos)
        ax.imshow(mpimg.imread(buf))
        ax.axis("off")

    y0 = 0.15
    fig.text(0.06, y0, "Perfiles similares", fontsize=11, fontweight="bold", color=viz.INK, va="top")
    for i, (_, s) in enumerate(sims.iterrows()):
        fig.text(
            0.06,
            y0 - 0.021 - 0.0175 * i,
            f"{s['similarity']:.3f}   {s['player']}  ({s['team']}, {s['primary_position']})",
            fontsize=8.5,
            color=viz.INK_2,
            va="top",
        )

    fig.text(0.54, y0, "Mejores destinos (encaje)", fontsize=11, fontweight="bold", color=viz.INK, va="top")
    for i, (_, d) in enumerate(destinos.iterrows()):
        fig.text(
            0.54,
            y0 - 0.021 - 0.0175 * i,
            f"{d['encaje']:.0f}   {d['team']}  (estilo {d['estilo']:+.2f}, mejora {d['mejora_puesto']:+.0f})",
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
    return out.getvalue()


def ficha_report_pdf(ficha: dict | None, ficha_sm: dict | None, query: str) -> bytes:
    """PDF de una página para un jugador fuera de los open data cargados.

    Sin eventos con coordenadas no hay radar, mapas ni encaje — pero la
    biografía de TheSportsDB y las estadísticas de temporada de Sportmonks
    (si hay token) ya bastan para una ficha presentable. `ficha` y
    `ficha_sm` pueden venir ambas a None si ningún servicio tuvo datos;
    el PDF se genera igual, dejándolo dicho.
    """
    viz.use_theme("light")
    nombre = (ficha or {}).get("nombre") or (ficha_sm or {}).get("nombre") or query
    foto_url = (ficha or {}).get("foto") or (ficha_sm or {}).get("foto")

    fig = plt.figure(figsize=(8.27, 11.69))  # A4 vertical
    fig.set_facecolor(viz.SURFACE)

    _embed_photo(fig, foto_url, (0.06, 0.86, 0.18, 0.11))

    # Layout de posiciones fijas (no calculadas a partir de la longitud del
    # texto): así la tabla de abajo nunca se solapa con una biografía larga.
    fig.text(0.28, 0.955, nombre, fontsize=22, fontweight="bold", color=viz.INK, va="top")
    if ficha:
        subtitulo = " · ".join(
            str(v) for v in (ficha.get("equipo"), ficha.get("posicion"), ficha.get("nacionalidad")) if v
        )
        if subtitulo:
            fig.text(0.28, 0.91, subtitulo, fontsize=12, color=viz.INK_2, va="top")
        detalles = " · ".join(
            str(v) for v in (ficha.get("nacimiento"), ficha.get("lugar_nacimiento"), ficha.get("altura")) if v
        )
        if detalles:
            fig.text(0.28, 0.88, detalles, fontsize=10, color=viz.MUTED, va="top")

    fig.text(
        0.06,
        0.83,
        "Ficha de scouting compuesta a partir de fuentes públicas (biografía de TheSportsDB, "
        "estadísticas de temporada de Sportmonks). Al no ser un jugador de los open data "
        "cargados en la app, no hay eventos con coordenadas de jugada: sin ellos no se puede "
        "calcular radar de percentiles, mapas de calor/tiros/pases ni el motor de encaje.",
        fontsize=7.5,
        color=viz.MUTED,
        va="top",
        wrap=True,
    )

    if ficha and ficha.get("descripcion"):
        fig.text(
            0.06,
            0.78,
            "Biografía (TheSportsDB, en inglés)",
            fontsize=11,
            fontweight="bold",
            color=viz.INK,
            va="top",
        )
        texto = ficha["descripcion"]
        texto = texto[:700] + ("…" if len(texto) > 700 else "")
        fig.text(0.06, 0.755, texto, fontsize=8.5, color=viz.INK_2, va="top", wrap=True, ha="left")

    temporadas = (ficha_sm or {}).get("temporadas") or []
    if temporadas:
        fig.text(
            0.06,
            0.48,
            "Estadísticas de temporada (Sportmonks)",
            fontsize=11,
            fontweight="bold",
            color=viz.INK,
            va="top",
        )
        fig.text(
            0.06,
            0.458,
            "Totales por club y temporada. Apariciones = partidos jugados (titular o suplente); "
            "titularidades = partidos de inicio; goles encajados y porterías a cero solo aplican "
            "a porteros.",
            fontsize=7,
            color=viz.MUTED,
            va="top",
            wrap=True,
        )
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

        ax = fig.add_axes((0.06, 0.13, 0.86, 0.3))
        ax.axis("off")
        tbl = ax.table(cellText=table_data, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1, 1.5)
        for (row, _col), cell in tbl.get_celld().items():
            cell.set_edgecolor(viz.GRID)
            if row == 0:
                cell.set_facecolor(viz.SURFACE)
                cell.set_text_props(fontweight="bold", color=viz.INK)
            else:
                cell.set_facecolor(viz.SURFACE)
                cell.set_text_props(color=viz.INK_2)
    else:
        fig.text(
            0.06,
            0.48,
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
