"""Visualizaciones: radar de percentiles, mapa de calor, pases y tiros.

Identidad visual única para todo el proyecto (paleta validada para
accesibilidad/daltonismo): azul = protagonista, naranja = secundario,
grises para todo lo que no es dato.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from mplsoccer import Pitch, Radar, VerticalPitch
from scipy.ndimage import gaussian_filter

# Paleta validada (accesibilidad/daltonismo) en variante clara y oscura.
_LIGHT = {
    "SURFACE": "#fcfcfb",
    "INK": "#0b0b0b",
    "INK_2": "#52514e",
    "MUTED": "#898781",
    "GRID": "#e1e0d9",
    "BASELINE": "#c3c2b7",
    "BLUE": "#2a78d6",
    "ORANGE": "#eb6834",
    "RING": "#f0efec",
    "SEQ": ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
}
_DARK = {
    "SURFACE": "#1a1a19",
    "INK": "#ffffff",
    "INK_2": "#c3c2b7",
    "MUTED": "#898781",
    "GRID": "#2c2c2a",
    "BASELINE": "#383835",
    "BLUE": "#3987e5",
    "ORANGE": "#d95926",
    "RING": "#242423",
    "SEQ": ["#1a1a19", "#104281", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"],
}

SURFACE = INK = INK_2 = MUTED = GRID = BASELINE = BLUE = ORANGE = RING = ""
SEQ_BLUE = None


def use_theme(mode: str = "light") -> None:
    """Activa la paleta clara u oscura para todos los gráficos siguientes."""
    pal = _DARK if mode == "dark" else _LIGHT
    g = globals()
    for key, value in pal.items():
        if key != "SEQ":
            g[key] = value
    g["SEQ_BLUE"] = LinearSegmentedColormap.from_list("seq_blue", pal["SEQ"])


use_theme("light")

# Métricas del radar por grupo posicional: (columna de percentil, etiqueta)
RADAR_METRICS = {
    "FW": [
        ("npxg_p90_pct", "npxG"),
        ("shots_p90_pct", "Tiros"),
        ("xa_p90_pct", "xA"),
        ("key_passes_p90_pct", "Pases clave"),
        ("dribbles_cmp_p90_pct", "Regates"),
        ("touches_box_p90_pct", "Toques en área"),
        ("prog_carries_p90_pct", "Conducciones\nprogresivas"),
        ("prog_passes_p90_pct", "Pases\nprogresivos"),
        ("pressures_p90_pct", "Presiones"),
    ],
    "MF": [
        ("npxg_p90_pct", "npxG"),
        ("xa_p90_pct", "xA"),
        ("key_passes_p90_pct", "Pases clave"),
        ("prog_passes_p90_pct", "Pases\nprogresivos"),
        ("prog_carries_p90_pct", "Conducciones\nprogresivas"),
        ("dribbles_cmp_p90_pct", "Regates"),
        ("pressures_p90_pct", "Presiones"),
        ("padj_tack_int_p90_pct", "Entradas+Int.\n(PAdj)"),
        ("recoveries_p90_pct", "Recuperaciones"),
    ],
    "DF": [
        ("padj_tack_int_p90_pct", "Entradas+Int.\n(PAdj)"),
        ("blocks_p90_pct", "Bloqueos"),
        ("clearances_p90_pct", "Despejes"),
        ("recoveries_p90_pct", "Recuperaciones"),
        ("pressures_p90_pct", "Presiones"),
        ("prog_passes_p90_pct", "Pases\nprogresivos"),
        ("prog_carries_p90_pct", "Conducciones\nprogresivas"),
        ("xa_p90_pct", "xA"),
    ],
}
RADAR_METRICS["GK"] = RADAR_METRICS["DF"]


def _header(fig, title: str, subtitle: str) -> None:
    fig.text(0.06, 0.965, title, fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.06, 0.925, subtitle, fontsize=9.5, color=INK_2, va="top")


def save(fig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def radar_chart(player_row: pd.Series, competition_label: str, display: str | None = None):
    group = player_row["position_group"]
    metrics = RADAR_METRICS.get(group, RADAR_METRICS["MF"])
    params = [label for _, label in metrics]
    values = [float(player_row[col]) for col, _ in metrics]

    radar = Radar(
        params,
        min_range=[0] * len(params),
        max_range=[100] * len(params),
        round_int=[True] * len(params),
        num_rings=4,
        ring_width=1,
        center_circle_radius=1,
    )
    fig, ax = radar.setup_axis(figsize=(8, 8.6))
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    radar.draw_circles(ax=ax, facecolor=RING, edgecolor=GRID)
    radar.draw_radar(
        values,
        ax=ax,
        kwargs_radar={"facecolor": BLUE, "alpha": 0.55, "edgecolor": BLUE, "linewidth": 2},
        kwargs_rings={"facecolor": BLUE, "alpha": 0.08},
    )
    radar.draw_range_labels(ax=ax, fontsize=8, color=MUTED)
    radar.draw_param_labels(ax=ax, fontsize=10, color=INK)

    _header(
        fig,
        display or player_row["player"],
        f"{player_row['team']}  ·  {competition_label}  ·  {player_row['minutes']:.0f} min\n"
        f"Percentiles per-90 vs. {group} de la competición",
    )
    return fig


def radar_compare(
    row_a: pd.Series,
    row_b: pd.Series,
    competition_label: str,
    name_a: str | None = None,
    name_b: str | None = None,
):
    """Radar superpuesto de dos jugadores (percentiles del grupo del primero)."""
    import matplotlib.patches as mpatches

    name_a = name_a or row_a["player"]
    name_b = name_b or row_b["player"]
    group = row_a["position_group"]
    metrics = RADAR_METRICS.get(group, RADAR_METRICS["MF"])
    params = [label for _, label in metrics]
    values_a = [float(row_a[col]) for col, _ in metrics]
    values_b = [float(row_b[col]) for col, _ in metrics]

    radar = Radar(
        params,
        min_range=[0] * len(params),
        max_range=[100] * len(params),
        round_int=[True] * len(params),
        num_rings=4,
        ring_width=1,
        center_circle_radius=1,
    )
    fig, ax = radar.setup_axis(figsize=(8, 8.6))
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    radar.draw_circles(ax=ax, facecolor=RING, edgecolor=GRID)
    radar.draw_radar_compare(
        values_a,
        values_b,
        ax=ax,
        kwargs_radar={"facecolor": BLUE, "alpha": 0.5, "edgecolor": BLUE, "linewidth": 2},
        kwargs_compare={"facecolor": ORANGE, "alpha": 0.45, "edgecolor": ORANGE, "linewidth": 2},
    )
    radar.draw_range_labels(ax=ax, fontsize=8, color=MUTED)
    radar.draw_param_labels(ax=ax, fontsize=10, color=INK)
    ax.legend(
        handles=[
            mpatches.Patch(color=BLUE, alpha=0.7, label=name_a),
            mpatches.Patch(color=ORANGE, alpha=0.7, label=name_b),
        ],
        loc="upper right",
        fontsize=9,
        frameon=False,
        labelcolor=INK_2,
    )
    _header(
        fig,
        f"{name_a}  vs  {name_b}",
        f"{competition_label}  ·  Percentiles per-90 vs. {group} de la competición",
    )
    return fig


def style_map(
    style: pd.DataFrame,
    highlight: list[str] | None = None,
    current_team: str | None = None,
    subtitle: str = "",
):
    """Mapa de estilo de la competición: posesión vs presión, tamaño ∝ verticalidad.

    `style` es la salida de fit.team_style (indexada por equipo). Los equipos en
    `highlight` (p. ej. los mejores destinos de un jugador) van en azul; el
    equipo actual, en naranja; el resto, en gris.
    """
    highlight = highlight or []
    fig, ax = plt.subplots(figsize=(9, 6.4))
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    sizes = 60 + 14 * (style["prog_share"].fillna(style["prog_share"].median()))
    for team, row in style.iterrows():
        if team == current_team:
            color, z = ORANGE, 3
        elif team in highlight:
            color, z = BLUE, 3
        else:
            color, z = MUTED, 2
        ax.scatter(
            row["possession"],
            row["ppda"],
            s=float(sizes.loc[team]),
            facecolor=color,
            edgecolor=SURFACE,
            linewidth=0.8,
            alpha=0.85,
            zorder=z,
        )
        destacado = team in highlight or team == current_team
        ax.annotate(
            team,
            (row["possession"], row["ppda"]),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=8 if destacado else 7,
            fontweight="bold" if destacado else "normal",
            color=INK if destacado else INK_2,
            zorder=4,
        )

    ax.invert_yaxis()  # arriba = más presión (PPDA bajo)
    ax.set_xlabel("Posesión (%)", fontsize=9, color=INK_2)
    ax.set_ylabel("PPDA (↑ más presión)", fontsize=9, color=INK_2)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.6)

    handles = [
        Line2D([], [], marker="o", ls="", mfc=BLUE, mec=SURFACE, ms=9, label="Mejores destinos"),
        Line2D([], [], marker="o", ls="", mfc=ORANGE, mec=SURFACE, ms=9, label="Equipo actual"),
        Line2D([], [], marker="o", ls="", mfc=MUTED, mec=SURFACE, ms=9, label="Resto"),
    ]
    ax.legend(handles=handles, loc="best", fontsize=8, frameon=False, labelcolor=INK_2)

    _header(fig, "Mapa de estilo de la competición", subtitle + "  ·  tamaño ∝ % pases progresivos")
    fig.subplots_adjust(top=0.86)
    return fig


def calibration_chart(cal_own: pd.DataFrame, cal_sb: pd.DataFrame, subtitle: str = ""):
    """Curva de fiabilidad: xG medio predicho vs frecuencia real de gol por tramo."""
    fig, ax = plt.subplots(figsize=(7.5, 6))
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    tope = 0.05
    for df in (cal_own, cal_sb):
        if not df.empty:
            tope = max(tope, float(df[["pred", "obs"]].max().max()))
    tope = min(1.0, tope * 1.15)
    ax.plot([0, tope], [0, tope], ls="--", lw=1, color=BASELINE, zorder=1)

    for df, color, label in ((cal_own, BLUE, "xG propio"), (cal_sb, ORANGE, "xG StatsBomb")):
        if df.empty:
            continue
        ax.plot(df["pred"], df["obs"], color=color, lw=2, marker="o", ms=5, label=label, zorder=3)

    ax.set_xlim(0, tope)
    ax.set_ylim(0, tope)
    ax.set_xlabel("xG medio predicho en el tramo", fontsize=9, color=INK_2)
    ax.set_ylabel("Frecuencia real de gol", fontsize=9, color=INK_2)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.6)
    ax.legend(loc="upper left", fontsize=9, frameon=False, labelcolor=INK_2)

    _header(fig, "Curva de calibración", subtitle + "  ·  la diagonal es la calibración perfecta")
    fig.subplots_adjust(top=0.86)
    return fig


def xg_scatter(shots: pd.DataFrame, subtitle: str = ""):
    """xG propio (out-of-fold) frente al xG del proveedor, tiro a tiro."""
    fig, ax = plt.subplots(figsize=(7.5, 6))
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    datos = shots.dropna(subset=["sb_xg", "xg_own"])
    tope = min(1.0, float(datos[["sb_xg", "xg_own"]].max().max()) * 1.1) if not datos.empty else 1.0
    ax.plot([0, tope], [0, tope], ls="--", lw=1, color=BASELINE, zorder=1)
    ax.scatter(datos["sb_xg"], datos["xg_own"], s=24, facecolor=BLUE, alpha=0.45, edgecolor="none", zorder=2)

    ax.set_xlim(0, tope)
    ax.set_ylim(0, tope)
    ax.set_xlabel("xG de StatsBomb", fontsize=9, color=INK_2)
    ax.set_ylabel("xG propio (out-of-fold)", fontsize=9, color=INK_2)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.6)

    _header(fig, "xG propio vs xG del proveedor", subtitle)
    fig.subplots_adjust(top=0.86)
    return fig


def _player_events(events: pd.DataFrame, player: str) -> pd.DataFrame:
    ev = events[(events["player"] == player) & (events["period"] <= 4)]
    return ev[ev["location"].notna()]


def touch_heatmap(events: pd.DataFrame, player: str, competition_label: str, display: str | None = None):
    ev = _player_events(events, player)
    touches = ev[ev["type"].isin(["Pass", "Shot", "Carry", "Dribble", "Ball Receipt*"])]
    x = touches["location"].str[0].astype(float)
    y = touches["location"].str[1].astype(float)

    pitch = Pitch(pitch_type="statsbomb", pitch_color=SURFACE, line_color=BASELINE, linewidth=1)
    fig, ax = pitch.draw(figsize=(10, 7.4))
    fig.set_facecolor(SURFACE)
    stats = pitch.bin_statistic(x, y, statistic="count", bins=(30, 20))
    stats["statistic"] = gaussian_filter(stats["statistic"], 1.5)
    pitch.heatmap(stats, ax=ax, cmap=SEQ_BLUE, edgecolors="none", zorder=0)

    _header(
        fig,
        display or player,
        f"{competition_label}  ·  Mapa de calor de toques ({len(touches)})  ·  ataca →",
    )
    return fig


def pass_map(events: pd.DataFrame, player: str, competition_label: str, display: str | None = None):
    """Pases progresivos (azul) y pases que generaron tiro (naranja)."""
    from .metrics import SET_PIECE_PASS_TYPES, is_progressive

    ev = _player_events(events, player)
    passes = ev[(ev["type"] == "Pass") & ev["pass_end_location"].notna()].copy()
    completed = passes[passes["pass_outcome"].isna()] if "pass_outcome" in passes.columns else passes
    if "pass_type" in completed.columns:
        open_play = completed[~completed["pass_type"].isin(SET_PIECE_PASS_TYPES)]
    else:
        open_play = completed

    prog = open_play[is_progressive(open_play["location"], open_play["pass_end_location"])]
    key_mask = pd.Series(False, index=passes.index)
    for c in ("pass_shot_assist", "pass_goal_assist"):
        if c in passes.columns:
            key_mask |= passes[c].eq(True)
    key = passes[key_mask]
    prog = prog[~prog.index.isin(key.index)]

    pitch = Pitch(pitch_type="statsbomb", pitch_color=SURFACE, line_color=BASELINE, linewidth=1)
    fig, ax = pitch.draw(figsize=(10, 7.4))
    fig.set_facecolor(SURFACE)

    for df, color, alpha in ((prog, BLUE, 0.45), (key, ORANGE, 0.85)):
        if df.empty:
            continue
        pitch.lines(
            df["location"].str[0].astype(float),
            df["location"].str[1].astype(float),
            df["pass_end_location"].str[0].astype(float),
            df["pass_end_location"].str[1].astype(float),
            comet=True,
            color=color,
            linewidth=3,
            alpha=alpha,
            ax=ax,
            zorder=2,
        )

    handles = [
        Line2D([], [], color=BLUE, lw=3, label=f"Progresivos ({len(prog)})"),
        Line2D([], [], color=ORANGE, lw=3, label=f"Generaron tiro ({len(key)})"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=False, labelcolor=INK_2)

    _header(fig, display or player, f"{competition_label}  ·  Pases progresivos y pases clave  ·  ataca →")
    return fig


def shot_map(events: pd.DataFrame, player: str, competition_label: str, display: str | None = None):
    ev = _player_events(events, player)
    shots = ev[(ev["type"] == "Shot") & (ev.get("shot_type") != "Penalty")].copy()
    goals = shots[shots["shot_outcome"] == "Goal"]
    misses = shots[shots["shot_outcome"] != "Goal"]

    pitch = VerticalPitch(
        pitch_type="statsbomb", half=True, pitch_color=SURFACE, line_color=BASELINE, linewidth=1
    )
    fig, ax = pitch.draw(figsize=(8.6, 7.4))
    fig.set_facecolor(SURFACE)

    def _plot(df, **kw):
        if df.empty:
            return
        pitch.scatter(
            df["location"].str[0].astype(float),
            df["location"].str[1].astype(float),
            s=df["shot_statsbomb_xg"].fillna(0) * 900 + 40,
            ax=ax,
            zorder=2,
            **kw,
        )

    _plot(misses, facecolor="none", edgecolor=MUTED, linewidth=1.4)
    _plot(goals, facecolor=BLUE, edgecolor=SURFACE, linewidth=1, alpha=0.9)

    handles = [
        Line2D([], [], marker="o", ls="", mfc=BLUE, mec=SURFACE, ms=10, label=f"Gol ({len(goals)})"),
        Line2D([], [], marker="o", ls="", mfc="none", mec=MUTED, ms=10, label=f"Sin gol ({len(misses)})"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=False, labelcolor=INK_2)

    npxg = shots["shot_statsbomb_xg"].fillna(0).sum()
    _header(
        fig,
        display or player,
        f"{competition_label}  ·  Tiros sin penaltis: {len(shots)}  ·  npxG {npxg:.2f}  ·  "
        f"goles {len(goals)}  ·  tamaño ∝ xG",
    )
    return fig
