"""Contratos de los looks que separan color y brillo por energia."""

from __future__ import annotations

import colorsys
from dataclasses import replace

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import EFFECTS, get_effect
from huebpm.state import AudioState

ANCHOR = 100.0
PERIOD = 0.5
CAMPOS_NUEVOS = ("sub_bass", "beat_strength", "onset_rate")


def contexto(
    *,
    bands: tuple[float, float, float] = (0.9, 0.3, 0.1),
    hue: float = 0.0,
    tonality: float = 0.5,
    phase: float = 0.0,
    channel_count: int = 2,
    **state_fields: float,
) -> RenderContext:
    clock = BeatClock()
    clock.update(
        TempoEstimate(bpm=120.0, period=PERIOD, last_beat_time=ANCHOR, confidence=1.0),
        ANCHOR,
    )
    return RenderContext(
        now=ANCHOR + phase * PERIOD,
        state=AudioState(
            bands=np.array(bands), chroma_hue=hue, tonality=tonality, locked=True, **state_fields
        ),
        clock=clock,
        channel_count=channel_count,
        cfg=EffectsConfig(),
        render_fps=50.0,
    )


def brillo(color: tuple[float, float, float]) -> float:
    return max(color)


def matiz(color: tuple[float, float, float]) -> float:
    return colorsys.rgb_to_hsv(*color)[0]


def test_los_nuevos_looks_se_registran():
    assert {"wash", "harmony_energy"} <= set(EFFECTS)
    assert get_effect("wash").name == "wash"
    assert get_effect("harmony_energy").name == "harmony_energy"


def test_wash_conserva_el_matiz_y_sigue_la_energia():
    bajo = get_effect("wash").render(contexto(bands=(0.1, 0.0, 0.0)))[0]
    alto = get_effect("wash").render(contexto(bands=(0.0, 0.0, 0.8)))[0]

    assert matiz(bajo) == pytest.approx(matiz(alto), abs=1e-12)
    assert brillo(alto) > brillo(bajo) + 0.5


def test_wash_transmite_mas_salto_de_energia_que_harmony():
    """El wash deliberadamente no amortigua la envolvente de energia."""
    material = [
        contexto(bands=(energy, 0.0, 0.0), hue=0.0, tonality=1.0)
        for energy in (0.10, 0.35, 0.05, 0.80, 0.20)
    ]

    def maximo_salto(look: str) -> float:
        brillo_por_frame = [brillo(get_effect(look).render(ctx)[0]) for ctx in material]
        return float(np.abs(np.diff(brillo_por_frame)).max())

    wash_jump = maximo_salto("wash")
    harmony_jump = maximo_salto("harmony")

    assert wash_jump > harmony_jump + 0.5


def test_harmony_energy_separa_color_de_acorde_y_brillo_de_energia():
    efecto = get_effect("harmony_energy")
    rojo = efecto.render(contexto(hue=0.0, bands=(0.5, 0.1, 0.0)))[0]
    cian = efecto.render(contexto(hue=0.5, bands=(0.5, 0.1, 0.0)))[0]
    bajo = efecto.render(contexto(hue=0.0, bands=(0.1, 0.0, 0.0)))[0]
    alto = efecto.render(contexto(hue=0.0, bands=(0.8, 0.0, 0.0)))[0]

    assert matiz(rojo) != pytest.approx(matiz(cian), abs=0.1)
    assert matiz(bajo) == pytest.approx(matiz(alto), abs=1e-12)
    assert brillo(alto) > brillo(bajo) + 0.5


def test_harmony_energy_degrada_a_espectro_sin_tonalidad():
    ctx = contexto(tonality=0.0, bands=(0.1, 0.3, 0.8))
    assert get_effect("harmony_energy").render(ctx) == pytest.approx(
        get_effect("spectrum").render(ctx)
    )


@pytest.mark.parametrize("look", ("wash", "harmony_energy"))
def test_los_looks_cenitales_no_saltan_con_el_reloj_a_120_bpm(look):
    ctx = contexto()
    effect = get_effect(look)
    values = [
        brillo(effect.render(replace(ctx, now=ANCHOR + frame / 50.0))[0])
        for frame in range(int(PERIOD * 50) + 1)
    ]

    assert np.abs(np.diff(values)).max() <= 0.05


@pytest.mark.parametrize("look", ("wash", "harmony_energy"))
@pytest.mark.parametrize("field", CAMPOS_NUEVOS)
def test_los_nuevos_looks_ignoran_las_senales_de_composicion(look, field):
    ctx = contexto(**{field: 0.0})
    apagado = get_effect(look).render(ctx)
    encendido = get_effect(look).render(replace(ctx, state=replace(ctx.state, **{field: 1.0})))
    assert apagado == pytest.approx(encendido, abs=1e-12)
