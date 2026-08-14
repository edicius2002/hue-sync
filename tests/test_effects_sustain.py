"""Tests del modo de brillo sostenido.

La propiedad que hay que clavar: con mezcla 0 el modo rinde EXACTAMENTE como
envolvente de beat. Es la degradacion segura (detector aun no cableado, o
material percusivo / cama de ruido) y el unico sitio donde un error se veria
como un fogonazo al cruzar el umbral.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import (
    RenderContext,
    beat_envelope,
    gentle_brightness,
    spectrum_color,
    sustain_mix,
)
from huebpm.effects.modes import EFFECTS, get_effect
from huebpm.state import AudioState

ANCHOR = 100.0
FASES = (0.0, 0.25, 0.5, 0.75, 0.99)


def make_ctx(
    phase: float = 0.0,
    *,
    sustain: float = 0.0,
    tonality: float = 0.0,
    locked: bool = True,
    cfg: EffectsConfig | None = None,
    bpm: float = 120.0,
    bands: tuple[float, float, float] = (0.9, 0.3, 0.1),
) -> RenderContext:
    cfg = cfg or EffectsConfig()
    period = 60.0 / bpm
    clock = BeatClock()
    if locked:
        clock.update(
            TempoEstimate(bpm=bpm, period=period, last_beat_time=ANCHOR, confidence=1.0),
            ANCHOR,
        )
    return RenderContext(
        now=ANCHOR + phase * period,
        state=AudioState(
            bands=np.array(bands),
            locked=locked,
            sustain=sustain,
            tonality=tonality,
        ),
        clock=clock,
        channel_count=1,
        cfg=cfg,
        render_fps=50.0,
    )


def color_por_envolvente(ctx: RenderContext, brillo: float) -> tuple[float, float, float]:
    return tuple(c * brillo for c in spectrum_color(ctx))


# --- sustain_mix: fronteras y producto ---------------------------------------


def test_sostenido_bajo_mezcla_cero():
    """Sin sostenido no hay modo continuo, aunque la tonalidad este al maximo."""
    cfg = EffectsConfig()
    assert sustain_mix(make_ctx(sustain=0.0, tonality=1.0, cfg=cfg)) == 0.0
    assert sustain_mix(make_ctx(sustain=cfg.sustain_min, tonality=1.0, cfg=cfg)) == 0.0
    assert sustain_mix(make_ctx(sustain=cfg.sustain_min - 1e-6, tonality=1.0, cfg=cfg)) == 0.0


def test_tonalidad_baja_mezcla_cero():
    """Cama de ruido: sustain crudo alto, pero sin armonia no cuenta."""
    cfg = EffectsConfig()
    assert sustain_mix(make_ctx(sustain=1.0, tonality=0.0, cfg=cfg)) == 0.0
    assert sustain_mix(make_ctx(sustain=1.0, tonality=cfg.sustain_min_tonality, cfg=cfg)) == 0.0
    assert sustain_mix(make_ctx(sustain=1.0, tonality=0.04, cfg=cfg)) == 0.0


def test_ambos_altos_mezcla_uno():
    cfg = EffectsConfig()
    assert sustain_mix(make_ctx(sustain=1.0, tonality=1.0, cfg=cfg)) == 1.0
    assert (
        sustain_mix(
            make_ctx(sustain=cfg.sustain_full, tonality=cfg.sustain_full_tonality, cfg=cfg)
        )
        == 1.0
    )


def test_la_mezcla_es_progresiva():
    """Regresion del umbral duro: a mitad de ambas rampas no es 0 ni 1."""
    cfg = EffectsConfig()
    medio_s = (cfg.sustain_min + cfg.sustain_full) / 2
    medio_t = (cfg.sustain_min_tonality + cfg.sustain_full_tonality) / 2
    mix = sustain_mix(make_ctx(sustain=medio_s, tonality=medio_t, cfg=cfg))
    assert 0.2 < mix < 0.3


def test_el_producto_no_es_un_min():
    """A mitad de las dos rampas, min() daria 0.5 y el producto 0.25.

    Esa diferencia es el pliegue que se ve como fogonazo: min() cambia de
    restriccion activa en la diagonal, el producto no.
    """
    cfg = EffectsConfig()
    medio_s = (cfg.sustain_min + cfg.sustain_full) / 2
    medio_t = (cfg.sustain_min_tonality + cfg.sustain_full_tonality) / 2
    mix = sustain_mix(make_ctx(sustain=medio_s, tonality=medio_t, cfg=cfg))
    assert mix == pytest.approx(0.25)
    assert mix != pytest.approx(0.5)


def test_una_rampa_a_mitad_y_la_otra_llena():
    cfg = EffectsConfig()
    medio_s = (cfg.sustain_min + cfg.sustain_full) / 2
    assert sustain_mix(
        make_ctx(sustain=medio_s, tonality=1.0, cfg=cfg)
    ) == pytest.approx(0.5)
    medio_t = (cfg.sustain_min_tonality + cfg.sustain_full_tonality) / 2
    assert sustain_mix(
        make_ctx(sustain=1.0, tonality=medio_t, cfg=cfg)
    ) == pytest.approx(0.5)


def test_mezcla_acotada_a_cero_uno():
    for sustain in (-1.0, 0.0, 0.35, 0.5, 0.65, 1.0, 2.0):
        for tonality in (-1.0, 0.0, 0.08, 0.14, 0.20, 1.0, 2.0):
            mix = sustain_mix(make_ctx(sustain=sustain, tonality=tonality))
            assert 0.0 <= mix <= 1.0


# --- degradacion a envolvente de beat ----------------------------------------


@pytest.mark.parametrize("fase", FASES)
@pytest.mark.parametrize(
    "sustain,tonality",
    [
        (0.0, 0.0),
        (0.0, 1.0),
        (1.0, 0.0),
        (0.35, 1.0),
        (1.0, 0.08),
        (0.34, 1.0),
        (1.0, 0.07),
    ],
)
def test_mezcla_cero_rinde_exactamente_como_envolvente_de_beat(fase, sustain, tonality):
    """La propiedad obligatoria: ni un bit distinto de beat_envelope * color."""
    ctx = make_ctx(fase, sustain=sustain, tonality=tonality)
    assert sustain_mix(ctx) == 0.0
    obtenido = get_effect("sustain").render(ctx)[0]
    esperado = color_por_envolvente(ctx, beat_envelope(ctx))
    assert obtenido == pytest.approx(esperado, abs=1e-12)


def test_cama_de_ruido_tambien_degrada_a_beat():
    """Sustain crudo al maximo no enciende el modo si no hay armonia."""
    ctx = make_ctx(0.5, sustain=1.0, tonality=0.04)
    assert sustain_mix(ctx) == 0.0
    obtenido = get_effect("sustain").render(ctx)[0]
    esperado = color_por_envolvente(ctx, beat_envelope(ctx))
    assert obtenido == pytest.approx(esperado, abs=1e-12)


# --- extremo continuo e interpolacion ----------------------------------------


@pytest.mark.parametrize("fase", FASES)
def test_mezcla_uno_es_exactamente_brillo_continuo(fase):
    ctx = make_ctx(fase, sustain=1.0, tonality=1.0)
    assert sustain_mix(ctx) == 1.0
    continuo = gentle_brightness(ctx, 1.0, ctx.cfg.harmony_max_step)
    obtenido = get_effect("sustain").render(ctx)[0]
    esperado = color_por_envolvente(ctx, continuo)
    assert obtenido == pytest.approx(esperado, abs=1e-12)


def test_la_mezcla_interpola_las_dos_envolventes():
    cfg = EffectsConfig()
    medio_s = (cfg.sustain_min + cfg.sustain_full) / 2
    ctx = make_ctx(0.5, sustain=medio_s, tonality=1.0, cfg=cfg)
    mezcla = sustain_mix(ctx)
    assert mezcla == pytest.approx(0.5)

    destello = beat_envelope(ctx)
    continuo = gentle_brightness(ctx, 1.0, cfg.harmony_max_step)
    brillo = destello + (continuo - destello) * mezcla
    obtenido = get_effect("sustain").render(ctx)[0]
    assert obtenido == pytest.approx(color_por_envolvente(ctx, brillo), abs=1e-12)
    # En el valle del beat, el continuo esta por encima del destello: si no,
    # interpolar no se notaria.
    assert continuo > destello


def test_entre_golpes_el_sostenido_queda_mas_brillante_que_el_destello():
    """A fase 0.5 la envolvente de pico ya se ha caido; el continuo no."""
    destello = make_ctx(0.5, sustain=0.0, tonality=1.0)
    continuo = make_ctx(0.5, sustain=1.0, tonality=1.0)
    brillo_destello = max(get_effect("sustain").render(destello)[0])
    brillo_continuo = max(get_effect("sustain").render(continuo)[0])
    assert brillo_continuo > brillo_destello + 0.2


@pytest.mark.parametrize("bpm", [76.0, 120.0, 174.0])
def test_la_pendiente_se_acota_en_sostenido_pleno(bpm):
    """Misma razon que harmony: la fase avanza (BPM/60)/fps por frame."""
    cfg = EffectsConfig()
    ctx = make_ctx(0.0, sustain=1.0, tonality=1.0, cfg=cfg, bpm=bpm)
    efecto = get_effect("sustain")
    paso = 1.0 / 50.0
    brillos = [
        max(
            efecto.render(
                RenderContext(
                    now=ANCHOR + i * paso,
                    state=ctx.state,
                    clock=ctx.clock,
                    channel_count=1,
                    cfg=cfg,
                    render_fps=50.0,
                )
            )[0]
        )
        for i in range(int(50 * 60 / bpm) + 1)
    ]
    saltos = np.abs(np.diff(brillos))
    assert saltos.max() <= cfg.harmony_max_step + 0.002


def test_el_modo_esta_registrado():
    assert "sustain" in EFFECTS
    assert get_effect("sustain").name == "sustain"
