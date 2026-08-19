"""Contrato del escalon de paleta: que elija, y sobre todo que no parpadee."""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.palette import SpectrumStep, band_centroid
from huebpm.config import AnalysisConfig, EffectsConfig
from huebpm.effects.base import palette_color

BORDES = AnalysisConfig().spectrum_step_edges
FPS = 50.0
DT = 1.0 / FPS


def paso(**cambios) -> SpectrumStep:
    cfg = AnalysisConfig()
    opciones = {
        "edges": cfg.spectrum_step_edges,
        "tau": cfg.spectrum_step_tau,
        "margin": cfg.spectrum_step_margin,
        "dwell": cfg.spectrum_step_dwell,
    }
    opciones.update(cambios)
    return SpectrumStep(**opciones)


def correr(step: SpectrumStep, bandas, segundos: float) -> list[int]:
    return [step.update(bandas, DT) for _ in range(int(segundos * FPS))]


def test_solo_graves_da_el_primer_color_y_solo_agudos_el_ultimo():
    """Falla si la paleta deja de ir de grave a agudo."""
    assert paso().update((1.0, 0.0, 0.0), DT) == 0
    assert paso().update((0.0, 0.0, 1.0), DT) == len(BORDES)


def test_el_centroide_es_none_sin_energia():
    """Sin senal no hay decision posible, y eso no es lo mismo que cero."""
    assert band_centroid((0.0, 0.0, 0.0)) is None
    assert band_centroid((1.0, 0.0, 0.0)) == 0.0
    assert band_centroid((0.0, 0.0, 1.0)) == 1.0


def test_el_silencio_conserva_el_ultimo_color():
    """Falla si la luz salta de color al entrar o salir de un silencio."""
    step = paso()
    correr(step, (0.0, 0.0, 1.0), 2.0)
    ultimo = step.step
    assert ultimo == len(BORDES)
    assert correr(step, (0.0, 0.0, 0.0), 5.0) == [ultimo] * int(5.0 * FPS)


def test_el_primer_color_no_espera_la_permanencia():
    """La permanencia protege un color ya elegido; al arrancar no hay ninguno."""
    step = paso()
    assert step.update((0.0, 0.0, 1.0), DT) == len(BORDES)


def test_la_permanencia_acota_el_ritmo_de_cambio():
    """Falla si vuelve el estrobo: sin esto son 12 cambios por segundo.

    Se alterna el extremo grave y el extremo agudo en cada frame, que es la
    entrada mas hostil posible. El techo teorico es 1/dwell = 2 cambios/s.
    """
    step = paso(tau=0.0)
    indices = []
    for i in range(int(20.0 * FPS)):
        bandas = (1.0, 0.0, 0.0) if i % 2 else (0.0, 0.0, 1.0)
        indices.append(step.update(bandas, DT))

    cambios = sum(1 for a, b in zip(indices, indices[1:], strict=False) if a != b)
    assert cambios / 20.0 <= 1.0 / paso().dwell + 1e-9


def test_la_histeresis_ignora_un_cruce_que_no_pasa_del_margen():
    """Falla si un centroide pegado al borde hace ir y venir el color."""
    margen = 0.01
    step = paso(tau=0.0, margin=margen, dwell=0.0)
    dentro = BORDES[0] + margen / 2.0

    correr(step, (1.0, 0.0, 0.0), 1.0)
    assert step.step == 0
    # Un centroide `c` sale de bandas (1-c, 0, c): asi se pide uno exacto.
    assert step.update((1.0 - dentro, 0.0, dentro), DT) == 0
    # Justo pasado el primer borde mas el margen, y aun por debajo del segundo.
    fuera = BORDES[0] + margen * 2.0
    assert fuera < BORDES[1]
    assert step.update((1.0 - fuera, 0.0, fuera), DT) == 1


@pytest.mark.parametrize("indice,esperado", [(0, 0), (4, 4), (9, 4), (-3, 0)])
def test_palette_color_recorta_el_indice(indice, esperado):
    """Una paleta que no cuadre es un error de config, no una luz apagada."""
    from huebpm.analysis.beatclock import BeatClock
    from huebpm.effects.base import RenderContext
    from huebpm.state import AudioState

    cfg = EffectsConfig()
    ctx = RenderContext(
        now=0.0,
        state=AudioState(bands=np.zeros(3), spectrum_step=indice),
        clock=BeatClock(),
        channel_count=1,
        cfg=cfg,
    )
    assert palette_color(ctx) == cfg.spectrum_palette[esperado]


def test_todo_color_de_la_paleta_llega_a_uno():
    """El brillo del look es `max(RGB)`. Si un color no llega a 1.0, ese color
    seria mas oscuro que los demas al mismo nivel, y el recorte cenital estaria
    midiendo una escala distinta segun que color toque."""
    for color in EffectsConfig().spectrum_palette:
        assert max(color) == pytest.approx(1.0)
