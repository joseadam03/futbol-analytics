"""Test de humo del informe-CV en PDF, con datos sintéticos (sin red)."""

import io

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from PIL import Image

from futbol_analytics import fit, report


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def eventos() -> pd.DataFrame:
    def ev(team, player, type_, x=60.0, end=None, **kw):
        base = {
            "match_id": 1,
            "period": 1,
            "team": team,
            "player": player,
            "type": type_,
            "location": [x, 40.0],
            "pass_end_location": end,
            "pass_outcome": None,
            "pass_type": None,
            "pass_shot_assist": None,
            "shot_type": None,
            "shot_outcome": None,
            "shot_statsbomb_xg": None,
            "duel_type": None,
        }
        base.update(kw)
        return base

    rows = []
    rows += [ev("Equipo X", "Jugadora Test", "Pass", x=50.0, end=[95.0, 40.0])] * 3
    rows += [ev("Equipo X", "Jugadora Test", "Carry", x=55.0)]
    rows.append(
        ev(
            "Equipo X",
            "Jugadora Test",
            "Shot",
            x=110.0,
            shot_type="Open Play",
            shot_outcome="Goal",
            shot_statsbomb_xg=0.4,
        )
    )
    rows += [ev("Equipo Y", "Rival", "Pass", x=50.0, end=[60.0, 40.0])] * 4
    rows += [ev("Equipo Y", "Rival", "Pressure", x=60.0)] * 2
    return pd.DataFrame(rows)


def tabla() -> pd.DataFrame:
    pct = {c: 60.0 for c in fit.GROUP_KEY_PCT["FW"]}

    def fw(nombre, equipo, minutos=450.0):
        return {
            "player": nombre,
            "nickname": nombre,
            "team": equipo,
            "primary_position": "Center Forward",
            "position_group": "FW",
            "role": "Delantero",
            "minutes": minutos,
            "npxg_p90": 0.4,
            "xa_p90": 0.2,
            "prog_passes_p90": 3.0,
            "prog_carries_p90": 2.0,
            "dribbles_cmp_p90": 1.5,
            "touches_box_p90": 4.0,
            "pressures_p90": 5.0,
            "padj_tack_int_p90": 1.0,
            "recoveries_p90": 3.0,
            "pass_pct": 78.0,
            **pct,
        }

    return pd.DataFrame([fw("Jugadora Test", "Equipo X"), fw("S1", "Equipo Y"), fw("S2", "Equipo Y")])


def test_player_report_pdf_genera_un_pdf_valido():
    pdf = report.player_report_pdf(tabla(), eventos(), "Jugadora Test", "Competición Test")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 10_000  # contiene los cuatro paneles renderizados


def test_player_report_pdf_incrusta_foto_si_hay_url(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_bytes())
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url="https://img/x.png"
    )
    assert pdf[:5] == b"%PDF-"


def test_player_report_pdf_sin_foto_o_con_foto_rota_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: None)
    pdf = report.player_report_pdf(tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url=None)
    assert pdf[:5] == b"%PDF-"

    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: b"no es una imagen")
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url="https://img/roto.png"
    )
    assert pdf[:5] == b"%PDF-"

    # URL presente pero la descarga no trae nada (fallo transitorio, no excepción)
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: b"")
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url="https://img/vacia.png"
    )
    assert pdf[:5] == b"%PDF-"


def _png_de(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(80, 80, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_embed_photo_reduce_una_foto_de_baja_resolucion(monkeypatch):
    # avatar pequeño real (TheSportsDB/Sportmonks): estirarlo a la caja
    # completa lo dejaría pixelado, así que la caja se encoge en su lugar.
    # original=True: la caja que se pidió, antes de que matplotlib ajuste
    # la posición "activa" por su propio letterboxing de aspecto (aparte).
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(40, 40))
    fig = plt.figure(figsize=(8.27, 11.69))
    try:
        assert report._embed_photo(fig, "https://img/pequena.png", (0.06, 0.7, 0.3, 0.2))
        box = fig.axes[-1].get_position(original=True)
        assert box.width < 0.3
        assert box.height < 0.2
    finally:
        plt.close(fig)


def test_embed_photo_no_encoge_una_foto_de_alta_resolucion(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(2000, 2000))
    fig = plt.figure(figsize=(8.27, 11.69))
    try:
        assert report._embed_photo(fig, "https://img/grande.png", (0.06, 0.7, 0.3, 0.2))
        box = fig.axes[-1].get_position(original=True)
        assert box.width == pytest.approx(0.3)
        assert box.height == pytest.approx(0.2)
    finally:
        plt.close(fig)


def test_ficha_report_pdf_completa_con_foto_bio_y_temporadas(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_bytes())
    ficha = {
        "nombre": "Franculino Djú",
        "equipo": "Midtjylland",
        "posicion": "Forward",
        "nacionalidad": "Guinea-Bissau",
        "nacimiento": "2004-06-28",
        "lugar_nacimiento": "Bissau",
        "altura": "180 cm",
        "descripcion": "Texto biográfico de prueba. " * 30,
        "foto": "https://img/dju.png",
    }
    ficha_sm = {
        "nombre": "Franculino Djú",
        "foto": "https://img/dju_sm.png",
        "temporadas": [
            {"season_name": "2025/2026", "goals": 17.0, "assists": 4.0, "minutes": 1343.0},
            {"season_name": "2024/2025", "goals": 10.0, "assists": 2.0, "minutes": 1800.0},
        ],
    }
    pdf = report.ficha_report_pdf(ficha, ficha_sm, "Franculino Djú")
    assert pdf[:5] == b"%PDF-"


def test_ficha_report_pdf_sin_ningun_dato_no_revienta():
    pdf = report.ficha_report_pdf(None, None, "Jugador Desconocido")
    assert pdf[:5] == b"%PDF-"


def test_ficha_report_pdf_sin_biografia_no_deja_hueco(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_bytes())
    ficha = {
        "nombre": "Franculino Djú",
        "equipo": "Midtjylland",
        "posicion": "Forward",
        "nacionalidad": "Guinea-Bissau",
        "foto": "https://img/dju.png",
        # sin "descripcion": el caso real de este jugador en TheSportsDB
    }
    ficha_sm = {"nombre": "Franculino", "temporadas": [{"season_name": "2025/2026", "goals": 17.0}]}
    pdf = report.ficha_report_pdf(ficha, ficha_sm, "Franculino Djú")
    assert pdf[:5] == b"%PDF-"


def test_ficha_report_pdf_prefiere_el_nombre_mas_completo():
    # el display_name corto de una API no debe ganarle al nombre completo
    # que el usuario ya escribió en la búsqueda
    ficha_sm = {"nombre": "Franculino", "temporadas": []}
    pdf = report.ficha_report_pdf(None, ficha_sm, "Franculino Djú")
    assert pdf[:5] == b"%PDF-"


def test_header_band_incrusta_escudo_si_hay_url(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(300, 300))
    fig = plt.figure(figsize=(8.27, 11.69))
    try:
        n_antes = len(fig.axes)
        report._header_band(fig, "Título", height=0.075, crest_url="https://img/escudo.png")
        assert len(fig.axes) == n_antes + 2  # la franja de color + el escudo
    finally:
        plt.close(fig)


def test_header_band_sin_url_no_anade_ejes_de_escudo():
    fig = plt.figure(figsize=(8.27, 11.69))
    try:
        report._header_band(fig, "Título", height=0.075)
        assert len(fig.axes) == 1  # solo la franja
    finally:
        plt.close(fig)


def test_header_band_escudo_caido_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: None)
    fig = plt.figure(figsize=(8.27, 11.69))
    try:
        report._header_band(fig, "Título", height=0.075, crest_url="https://img/caido.png")
        assert len(fig.axes) == 1  # sin descarga, sin eje extra
    finally:
        plt.close(fig)


def test_player_report_pdf_con_escudo_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(300, 300))
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", crest_url="https://img/escudo.png"
    )
    assert pdf[:5] == b"%PDF-"


def test_ficha_report_pdf_con_escudo_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(300, 300))
    ficha_sm = {"nombre": "Franculino", "temporadas": []}
    pdf = report.ficha_report_pdf(None, ficha_sm, "Franculino Djú", crest_url="https://img/escudo.png")
    assert pdf[:5] == b"%PDF-"
