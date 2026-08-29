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

from . import fit, similarity, viz


def _fig_png(fig, dpi: int = 150) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def player_report_pdf(
    table: pd.DataFrame,
    events: pd.DataFrame,
    player: str,
    comp_label: str,
    display: str | None = None,
) -> bytes:
    """PDF de una página con el informe completo del jugador."""
    viz.use_theme("light")
    prow = table[table["player"] == player].iloc[0]
    apodo = prow.get("nickname")
    display = display or (apodo if isinstance(apodo, str) and apodo else player)

    rol = prow.get("role")
    pool = str(rol).lower() + "s" if prow.get("pct_basis") == "role" and isinstance(rol, str) else None

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
    fig.text(0.06, 0.978, display, fontsize=20, fontweight="bold", color=viz.INK, va="top")
    fig.text(0.06, 0.95, subtitulo, fontsize=10, color=viz.INK_2, va="top")
    resumen = (
        f"npxG/90 {prow['npxg_p90']:.2f} (p{prow['npxg_p90_pct']:.0f})    "
        f"xA/90 {prow['xa_p90']:.2f} (p{prow['xa_p90_pct']:.0f})    "
        f"Pases prog./90 {prow['prog_passes_p90']:.1f} (p{prow['prog_passes_p90_pct']:.0f})    "
        f"Presiones/90 {prow['pressures_p90']:.1f} (p{prow['pressures_p90_pct']:.0f})"
    )
    fig.text(0.06, 0.931, resumen, fontsize=9, color=viz.INK, va="top")

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
