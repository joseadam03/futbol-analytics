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


def test_photo_box_compone_recorte_transparente_sobre_el_panel_no_negro():
    # TheSportsDB sirve las fotos de jugador como recorte RGBA (fondo
    # transparente). Sin componer primero sobre el panel, Image.convert
    # ("RGB") deja los píxeles transparentes en negro puro: un halo
    # rectangular negro alrededor del recorte, visto en un informe real.
    transparente = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    resultado = report._photo_box(transparente, aspect_w=1.0, aspect_h=1.0, fade_frac=0.0)
    esquina = resultado.getpixel((0, 0))
    assert esquina == report._hex_to_rgb(report._PANEL)


def test_es_recorte_transparente_distingue_recorte_de_foto_opaca():
    # un recorte real de jugador (TheSportsDB): mitad transparente, mitad
    # opaca de sobra para superar el umbral del 2%.
    recorte = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    recorte.paste(Image.new("RGBA", (20, 10), (200, 150, 100, 255)), (0, 0))
    assert report._es_recorte_transparente(recorte)

    # una foto de agencia normal, aunque venga en modo RGBA, es opaca de
    # borde a borde (como la de Aaron Mooy) — no debe tratarse como recorte.
    opaca = Image.new("RGBA", (20, 20), (10, 10, 10, 255))
    assert not report._es_recorte_transparente(opaca)

    assert not report._es_recorte_transparente(Image.new("RGB", (20, 20), (10, 10, 10)))
    assert not report._es_recorte_transparente(None)


def _png_transparente(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (width, height // 2), (200, 150, 100, 255)), (0, 0))
    img.save(buf, format="PNG")
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
            "shots_p90": 2.5,
            "key_passes_p90": 1.2,
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


def eventos_portero() -> pd.DataFrame:
    def ev(type_, **kw):
        base = {
            "match_id": 1,
            "period": 1,
            "team": "Equipo X",
            "player": "Portero Test",
            "type": type_,
            "location": [6.0, 40.0],
            "pass_end_location": None,
            "pass_outcome": None,
            "pass_type": None,
            "pass_shot_assist": None,
            "shot_type": None,
            "shot_outcome": None,
            "shot_statsbomb_xg": None,
            "duel_type": None,
            "goalkeeper_type": None,
        }
        base.update(kw)
        return base

    rows = [ev("Pass", location=[10.0, 40.0], pass_end_location=[40.0, 40.0])] * 4
    rows += [ev("Goal Keeper", goalkeeper_type="Shot Saved")] * 3
    rows += [ev("Goal Keeper", goalkeeper_type="Goal Conceded")]
    rows += [ev("Goal Keeper", goalkeeper_type="Keeper Sweeper")] * 2
    rows += [ev("Goal Keeper", goalkeeper_type="Collected")] * 4
    rows += [ev("Goal Keeper", goalkeeper_type="Punch")]
    # fit.teams_for_player calcula el estilo del equipo rival a partir de
    # sus propios eventos (posesión, progresión...) — sin un segundo
    # equipo en los eventos, team_style() no tiene nada que comparar.
    rows += [
        ev("Pass", team="Equipo Y", player="Rival", location=[50.0, 40.0], pass_end_location=[60.0, 40.0])
    ] * 4
    return pd.DataFrame(rows)


def tabla_portero() -> pd.DataFrame:
    # viz.RADAR_METRICS["GK"] y las listas CON BALÓN/SIN BALÓN de portero
    # usan métricas propias (paradas, % de paradas, salidas, recogidas,
    # puños), no las de fit.GROUP_KEY_PCT["GK"] (pensada para el motor de
    # encaje) — de ahí no reutilizar ese fixture como en tabla().
    fila = {
        "player": "Portero Test",
        "nickname": "Portero Test",
        "team": "Equipo X",
        "primary_position": "Goalkeeper",
        "position_group": "GK",
        "role": "Portero",
        "minutes": 450.0,
        "saves_p90": 2.0,
        "save_pct": 75.0,
        "keeper_sweeper_p90": 1.0,
        "collected_p90": 3.0,
        "punches_p90": 0.5,
        "pass_pct": 82.0,
        "passes_cmp_p90": 20.0,
        "prog_passes_p90": 1.5,
        "saves_p90_pct": 70.0,
        "save_pct_pct": 65.0,
        "keeper_sweeper_p90_pct": 55.0,
        "collected_p90_pct": 60.0,
        "punches_p90_pct": 45.0,
        "pass_pct_pct": 50.0,
        "prog_passes_p90_pct": 40.0,
        "passes_cmp_p90_pct": 50.0,
    }
    return pd.DataFrame([fila])


def test_player_report_pdf_genera_un_pdf_valido():
    pdf = report.player_report_pdf(tabla(), eventos(), "Jugadora Test", "Competición Test")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 10_000  # dos páginas, con foto de cabecera, radar y cinco paneles


def test_player_report_pdf_portero_usa_metricas_propias():
    # antes de este cambio, GK reutilizaba directamente las métricas de DF
    # (viz.RADAR_METRICS["GK"] = RADAR_METRICS["DF"]) — un central no se
    # describe igual que un portero.
    pdf = report.player_report_pdf(tabla_portero(), eventos_portero(), "Portero Test", "Competición Test")
    assert pdf[:5] == b"%PDF-"


def test_player_report_pdf_incrusta_foto_si_hay_url(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_bytes())
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url="https://img/x.png"
    )
    assert pdf[:5] == b"%PDF-"


def test_player_report_pdf_con_recorte_transparente_no_revienta(monkeypatch):
    # pedido explícito de Jose: sin la caja rectangular de antes, un recorte
    # real (fondo transparente) se dibuja tal cual, directamente sobre el
    # fondo de la página — rama de código separada de la foto opaca normal.
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_transparente(40, 60))
    pdf = report.player_report_pdf(
        tabla(), eventos(), "Jugadora Test", "Competición Test", photo_url="https://img/recorte.png"
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


def test_embed_image_reduce_una_imagen_de_baja_resolucion(monkeypatch):
    # avatar pequeño real (TheSportsDB/Sportmonks): estirarlo a la caja
    # completa lo dejaría pixelado, así que la caja se encoge en su lugar.
    # original=True: la caja que se pidió, antes de que matplotlib ajuste
    # la posición "activa" por su propio letterboxing de aspecto (aparte).
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(40, 40))
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        assert report._embed_image(fig, "https://img/pequena.png", (0.06, 0.7, 0.3, 0.2))
        box = fig.axes[-1].get_position(original=True)
        assert box.width < 0.3
        assert box.height < 0.2
    finally:
        plt.close(fig)


def test_embed_image_no_encoge_una_imagen_de_alta_resolucion(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(2000, 2000))
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        assert report._embed_image(fig, "https://img/grande.png", (0.06, 0.7, 0.3, 0.2))
        box = fig.axes[-1].get_position(original=True)
        assert box.width == pytest.approx(0.3)
        assert box.height == pytest.approx(0.2)
    finally:
        plt.close(fig)


def test_embed_image_sin_url_no_dibuja_nada():
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        assert not report._embed_image(fig, None, (0.06, 0.7, 0.3, 0.2))
        assert len(fig.axes) == 0
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


def test_ficha_report_pdf_con_traspasos_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_bytes())
    ficha_sm = {
        "nombre": "Franculino Djú",
        "temporadas": [{"season_name": "2025/2026", "goals": 17.0}],
        "traspasos": [
            {"fecha": "2023-07-01", "origen": "Benfica U23", "destino": "FC Midtjylland", "importe": None},
            {
                "fecha": "2026-09-02",
                "origen": "FC Midtjylland",
                "destino": "Trabzonspor",
                "importe": 17000000,
            },
        ],
    }
    pdf = report.ficha_report_pdf(None, ficha_sm, "Franculino Djú")
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


def test_hero_band_incrusta_escudo_si_hay_url(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: _png_de(300, 300))
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        n_antes = len(fig.axes)
        report._hero_band(
            fig,
            "Nombre",
            "Posición",
            [("Equipo", "X")],
            None,
            "https://img/escudo.png",
            hero_h=0.27,
            photo_x0=0.335,
            photo_w=0.33,
        )
        assert len(fig.axes) == n_antes + 2  # foto de cabecera + escudo
    finally:
        plt.close(fig)


def test_hero_band_sin_escudo_no_anade_eje_extra():
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        n_antes = len(fig.axes)
        report._hero_band(
            fig,
            "Nombre",
            "Posición",
            [("Equipo", "X")],
            None,
            None,
            hero_h=0.27,
            photo_x0=0.335,
            photo_w=0.33,
        )
        assert len(fig.axes) == n_antes + 1  # solo la foto de cabecera (placeholder si no hay URL)
    finally:
        plt.close(fig)


def test_hero_band_escudo_caido_no_revienta(monkeypatch):
    monkeypatch.setattr(report.photos, "fetch_bytes", lambda url: None)
    fig = plt.figure(figsize=report.PAGE_SIZE)
    try:
        n_antes = len(fig.axes)
        report._hero_band(
            fig,
            "Nombre",
            "Posición",
            [("Equipo", "X")],
            None,
            "https://img/caido.png",
            hero_h=0.27,
            photo_x0=0.335,
            photo_w=0.33,
        )
        assert len(fig.axes) == n_antes + 1  # solo la foto (sin escudo, la descarga falló)
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
