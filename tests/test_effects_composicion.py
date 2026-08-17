"""Contrato de la capa que compone un look y una ganancia por canal."""

from __future__ import annotations

import colorsys
from dataclasses import replace

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.cli import sync
from huebpm.config import Config, EffectsConfig, apply_env_overrides, load_config
from huebpm.effects import base
from huebpm.effects import modes as effect_modes
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import EFFECTS, ComboEffect, get_effect
from huebpm.state import AudioState

ANCHOR = 100.0
PERIOD = 0.5
LOOKS = (
    "combo", "harmony", "bars", "beat_flash", "spectrum", "sustain", "idle",
    "wash", "harmony_energy",
)


def config_composicion(
    modes: tuple[str, ...] = ("combo", "harmony"),
    gain: tuple[float, ...] = (1.0, 1.0),
    **cambios,
) -> EffectsConfig:
    cfg = EffectsConfig(**cambios)
    cfg.channel_modes = modes
    cfg.channel_gain = gain
    return cfg


def make_ctx(
    *,
    cfg: EffectsConfig | None = None,
    channel_count: int = 2,
) -> RenderContext:
    clock = BeatClock()
    clock.update(
        TempoEstimate(bpm=120.0, period=PERIOD, last_beat_time=ANCHOR, confidence=1.0),
        ANCHOR,
    )
    return RenderContext(
        now=ANCHOR,
        state=AudioState(bands=np.array((0.9, 0.3, 0.1)), locked=True, tonality=0.5),
        clock=clock,
        channel_count=channel_count,
        cfg=cfg or config_composicion(),
        render_fps=50.0,
    )


def test_el_compositor_asigna_combo_y_harmony_sin_alterar_el_look():
    """Falla si el compositor usa el look equivocado o cambia su RGB."""
    ctx = make_ctx()
    compuesto = effect_modes.CompositionEffect(ComboEffect()).render(ctx)

    assert compuesto == {
        0: ComboEffect().render(ctx)[0],
        1: get_effect("harmony").render(ctx)[0],
    }


@pytest.mark.parametrize("look", LOOKS)
def test_cada_look_real_se_puede_asignar_a_un_canal(look):
    """Falla si un nombre registrado deja de poder componerse por canal."""
    ctx = make_ctx(cfg=config_composicion((look,), (1.0,)), channel_count=1)
    assert effect_modes.CompositionEffect(ComboEffect()).render(ctx)[0] == get_effect(look).render(ctx)[0]


def test_el_registro_contiene_los_looks_y_no_el_compositor():
    """Falla si un compositor entra al registro y hace posible la recursion."""
    assert tuple(EFFECTS) == LOOKS


def test_la_ganancia_multiplica_el_brillo_de_su_canal():
    """Falla si la ganancia se ignora o se aplica al canal equivocado."""
    ctx = make_ctx(cfg=config_composicion(("spectrum", "spectrum"), (0.5, 1.0)))
    canales = effect_modes.CompositionEffect(ComboEffect()).render(ctx)
    esperado = get_effect("spectrum").render(ctx)[0]

    assert canales[0] == pytest.approx(tuple(c * 0.5 for c in esperado))
    assert canales[1] == esperado


def test_ganancia_uno_y_mode_explicito_producen_un_espejo_exacto():
    """Falla si el atajo `--mode X` deja una ganancia o look configurado activo."""
    ctx = make_ctx()
    espejo = effect_modes.CompositionEffect(
        get_effect("spectrum"),
        channel_modes=("spectrum", "spectrum"),
        channel_gain=(1.0, 1.0),
    ).render(ctx)

    esperado = get_effect("spectrum").render(ctx)
    assert espejo == esperado
    assert np.linalg.norm(np.subtract(espejo[0], espejo[1])) == 0.0


@pytest.mark.parametrize(
    "modes,gain",
    [
        (("combo",), (1.0,)),
        (("combo", "harmony"), (1.0,)),
        (("combo", "desconocido"), (1.0, 1.0)),
        ((), ()),
        (("composicion", "combo"), (1.0, 1.0)),
        (("combo", "harmony"), (1.0, 1.01)),
    ],
)
def test_configuracion_invalida_degrada_el_area_entera_al_mode(modes, gain):
    """Falla si un canal queda sin RGB en vez de usar el fallback completo."""
    ctx = make_ctx(cfg=config_composicion(modes, gain))
    assert effect_modes.CompositionEffect(ComboEffect()).render(ctx) == ComboEffect().render(ctx)


def test_limit_slope_acota_brillo_y_conserva_el_matiz():
    """Falla si se recorta RGB por componente y desplaza el color cenital."""
    nuevo = {0: (0.1, 0.1, 0.1), 1: (0.8, 0.4, 0.2)}
    limitado = base.limit_slope((0.5, 0.25, 0.125), nuevo, 1, 0.1)

    assert limitado[1] == pytest.approx((0.6, 0.3, 0.15))
    assert max(limitado[1]) - 0.5 <= 0.1
    assert colorsys.rgb_to_hsv(*limitado[1])[0] == pytest.approx(colorsys.rgb_to_hsv(*nuevo[1])[0])


def test_limit_slope_no_recorta_el_primer_frame():
    """Falla si se inventa un brillo previo y oscurece el primer cuadro."""
    nuevo = {1: (0.8, 0.4, 0.2)}
    assert base.limit_slope(None, nuevo, 1, 0.03) == nuevo


def test_limit_slope_apaga_negro_desde_el_color_anterior():
    """Un gain cero no puede apagar el techo de 0.50 a negro en un frame.

    `max(RGB)` no permite reescalar negro. Se conserva el RGB anterior y se
    baja a 0.47: asi el apagado tarda los mismos frames seguros que la subida.
    """
    previo = (0.5, 0.25, 0.125)
    ctx = make_ctx(cfg=config_composicion(("combo", "harmony"), (1.0, 0.0)))
    nuevo = effect_modes.CompositionEffect(ComboEffect()).render(ctx)
    limitado = base.limit_slope(previo, nuevo, 1, 0.03)

    assert nuevo[1] == (0.0, 0.0, 0.0)
    assert limitado[1] == pytest.approx((0.47, 0.235, 0.1175))
    assert max(previo) - max(limitado[1]) <= 0.03 + 1e-12
    assert colorsys.rgb_to_hsv(*limitado[1])[0] == pytest.approx(colorsys.rgb_to_hsv(*previo)[0])


def test_ceiling_clamp_false_deja_el_frame_sin_recorte():
    """Falla si el opt-out cenital no llega a la etapa de salida."""
    cfg = config_composicion(ceiling_channel=1, ceiling_clamp=False)
    nuevo = {0: (0.1, 0.1, 0.1), 1: (0.8, 0.4, 0.2)}
    assert sync._limit_ceiling(nuevo, {1: (0.5, 0.25, 0.125)}, cfg) == nuevo


@pytest.mark.parametrize("look", LOOKS)
def test_el_guard_cenital_acota_todos_los_looks(look):
    """Falla si se desactiva la etapa que protege al techo a 50 fps."""
    cfg = config_composicion(
        (look, look), (1.0, 1.0), ceiling_channel=1, ceiling_max_step=0.03
    )
    ctx = make_ctx(cfg=cfg)
    compositor = effect_modes.CompositionEffect(ComboEffect())
    anteriores: dict[int, base.Color] = {}

    for frame in range(int(PERIOD * ctx.render_fps) + 1):
        canales = compositor.render(replace(ctx, now=ANCHOR + frame / ctx.render_fps))
        limitados = sync._limit_ceiling(canales, anteriores, cfg)
        if 1 in anteriores:
            assert abs(max(limitados[1]) - max(anteriores[1])) <= cfg.ceiling_max_step + 1e-12
        anteriores = limitados


def test_channel_modes_y_channel_gain_son_tuplas_en_yaml_y_entorno(tmp_path):
    """Falla si uno de los dos caminos deja una lista mutable en configuracion."""
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        "effects:\n  channel_modes: [spectrum, idle]\n  channel_gain: [0.6, 1.0]\n",
        encoding="utf-8",
    )
    desde_yaml = load_config(ruta).effects

    cfg = Config()
    apply_env_overrides(
        cfg,
        {
            "HUEBPM_EFFECTS_CHANNEL_MODES": '["spectrum", "idle"]',
            "HUEBPM_EFFECTS_CHANNEL_GAIN": "[0.6, 1.0]",
        },
    )

    assert desde_yaml.channel_modes == cfg.effects.channel_modes == ("spectrum", "idle")
    assert desde_yaml.channel_gain == cfg.effects.channel_gain == (0.6, 1.0)
