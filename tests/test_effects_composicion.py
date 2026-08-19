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
    "combo", "harmony", "spectrum", "sustain", "idle", "wash",
)


def config_composicion(
    modes: tuple[str, ...] = ("combo", "harmony"),
    **cambios,
) -> EffectsConfig:
    cfg = EffectsConfig(**cambios)
    cfg.channel_modes = modes
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
    ctx = make_ctx(cfg=config_composicion((look,)), channel_count=1)
    assert effect_modes.CompositionEffect(ComboEffect()).render(ctx)[0] == get_effect(look).render(ctx)[0]


def test_el_registro_contiene_los_looks_y_no_el_compositor():
    """Falla si un compositor entra al registro y hace posible la recursion."""
    assert tuple(EFFECTS) == LOOKS


def test_mode_explicito_produce_el_mismo_look_antes_de_la_salida():
    """Falla si `--mode X` deja activo un look configurado antes del pipeline."""
    ctx = make_ctx()
    espejo = effect_modes.CompositionEffect(
        get_effect("spectrum"),
        channel_modes=("spectrum", "spectrum"),
    ).render(ctx)

    esperado = get_effect("spectrum").render(ctx)
    assert espejo == esperado
    assert np.linalg.norm(np.subtract(espejo[0], espejo[1])) == 0.0


@pytest.mark.parametrize(
    "modes",
    [
        ("combo",),
        ("combo", "desconocido"),
        (),
        ("composicion", "combo"),
    ],
)
def test_configuracion_invalida_degrada_el_area_entera_al_mode(modes):
    """Falla si un canal queda sin RGB en vez de usar el fallback completo."""
    ctx = make_ctx(cfg=config_composicion(modes))
    assert effect_modes.CompositionEffect(ComboEffect()).render(ctx) == ComboEffect().render(ctx)


@pytest.mark.parametrize(
    "channel_range",
    (
        [0.45, 1.0],
        ((0.2,), (0.4, 1.0)),
        ((0.2, 0.5, 1.0), (0.4, 1.0)),
    ),
)
def test_controles_rechazan_formas_de_rango_invalidas_sin_lanzar(channel_range):
    """Falla si un config.yaml viejo hace que la validacion desempaquete mal."""
    cfg = config_composicion(channel_range=channel_range)
    assert sync._output_controls_valid(2, cfg) is False


def test_controles_rechazan_un_rango_invertido():
    """Falla si el minimo de brillo queda por encima del maximo."""
    cfg = config_composicion(channel_range=((1.0, 0.2), (0.4, 1.0)))
    assert sync._output_controls_valid(2, cfg) is False


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
    """Un look que cae a negro no puede apagar el techo de 0.50 en un frame.

    `max(RGB)` no permite reescalar negro. Se conserva el RGB anterior y se
    baja a 0.47: asi el apagado tarda los mismos frames seguros que la subida.
    """
    previo = (0.5, 0.25, 0.125)
    nuevo = {0: (0.4, 0.2, 0.1), 1: (0.0, 0.0, 0.0)}
    limitado = base.limit_slope(previo, nuevo, 1, 0.03)

    assert nuevo[1] == (0.0, 0.0, 0.0)
    assert limitado[1] == pytest.approx((0.47, 0.235, 0.1175))
    assert max(previo) - max(limitado[1]) <= 0.03 + 1e-12
    assert colorsys.rgb_to_hsv(*limitado[1])[0] == pytest.approx(colorsys.rgb_to_hsv(*previo)[0])


def test_channel_range_mueve_suelo_y_techo_sin_cambiar_el_matiz():
    """Un rango 0.25..1.0 sube un brillo 0.40 a 0.55 sin lavar su RGB."""
    color = (0.4, 0.2, 0.1)
    transformado = base.channel_range(color, 0.25, 1.0)

    assert transformado == pytest.approx((0.55, 0.275, 0.1375))
    assert colorsys.rgb_to_hsv(*transformado)[0] == pytest.approx(colorsys.rgb_to_hsv(*color)[0])


def test_channel_saturation_multiplica_la_saturacion_sin_mover_hue_ni_brillo():
    """La ganancia de saturacion actua en HSV, no sobre componentes RGB."""
    color = colorsys.hsv_to_rgb(0.31, 0.4, 0.8)
    transformado = base.channel_saturation(color, 2.0)
    hue, saturation, brillo = colorsys.rgb_to_hsv(*transformado)

    assert hue == pytest.approx(0.31)
    assert saturation == pytest.approx(0.8)
    assert brillo == pytest.approx(0.8)


def test_channel_hue_shift_preserva_la_distancia_circular_entre_dos_colores():
    """El offset no puede borrar que dos acordes distintos son distintos.

    El offset va explicito y no leido del config: lo que se fija aqui es el
    contrato de la funcion, que tiene que valer para cualquier valor. Los
    defaults arrancan neutros, asi que leerlos convertiria esto en una
    comprobacion de que 0.0 no hace nada.
    """
    offset = 0.08
    primero = colorsys.hsv_to_rgb(0.95, 0.8, 0.7)
    segundo = colorsys.hsv_to_rgb(0.12, 0.8, 0.7)
    desplazado_a = base.channel_hue_shift(primero, offset)
    desplazado_b = base.channel_hue_shift(segundo, offset)

    def distancia(a, b):  # noqa: ANN001
        recta = abs(a - b)
        return min(recta, 1.0 - recta)

    original = distancia(colorsys.rgb_to_hsv(*primero)[0], colorsys.rgb_to_hsv(*segundo)[0])
    movida = distancia(colorsys.rgb_to_hsv(*desplazado_a)[0], colorsys.rgb_to_hsv(*desplazado_b)[0])
    assert colorsys.rgb_to_hsv(*desplazado_a)[0] == pytest.approx((0.95 + offset) % 1.0)
    assert movida == pytest.approx(original)


def test_channel_normalize_mezcla_el_crudo_con_el_pico_de_referencia():
    """0.5 normaliza solo la mitad: conserva parte de la dinamica original."""
    transformado = base.channel_normalize((0.4, 0.2, 0.1), 0.8, 0.5)

    assert transformado == pytest.approx((0.45, 0.225, 0.1125))


def test_peak_reference_sube_en_un_frame_y_baja_lento_con_suelo():
    """El ataque evita sobrebrillo al entrar un pico; release 120 s no infla cortes."""
    cfg = EffectsConfig()
    suelo = base.next_peak(
        None, 0.2, 1 / 50,
        floor=cfg.channel_normalize_floor,
        release_seconds=cfg.channel_normalize_release,
    )
    pico = base.next_peak(
        suelo, 0.9, 1 / 50,
        floor=cfg.channel_normalize_floor,
        release_seconds=cfg.channel_normalize_release,
    )
    liberado = base.next_peak(
        pico, 0.2, 1 / 50,
        floor=cfg.channel_normalize_floor,
        release_seconds=cfg.channel_normalize_release,
    )

    assert suelo == 0.6
    assert pico == 0.9
    assert liberado == pytest.approx(0.9 * np.exp(-1 / (50 * 120)))
    assert liberado > 0.6


def test_ceiling_clamp_false_deja_el_frame_sin_recorte():
    """Falla si el opt-out cenital no llega a la etapa de salida."""
    cfg = config_composicion(ceiling_channel=1, ceiling_clamp=False)
    nuevo = {0: (0.1, 0.1, 0.1), 1: (0.8, 0.4, 0.2)}
    assert sync._limit_ceiling(nuevo, {1: (0.5, 0.25, 0.125)}, cfg) == nuevo


@pytest.mark.parametrize("look", LOOKS)
def test_el_guard_cenital_acota_todos_los_looks(look):
    """Falla si se desactiva la etapa que protege al techo a 50 fps."""
    cfg = config_composicion(
        (look, look), ceiling_channel=1, ceiling_max_step=0.03
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


@pytest.mark.parametrize("normalizacion", (0.0, 0.5, 1.0))
@pytest.mark.parametrize("look", LOOKS)
def test_el_guard_cenital_sigue_ultimo_despues_de_normalizar(look, normalizacion):
    """Rango, HSV y normalizacion no pueden reabrir un salto del techo."""
    cfg = config_composicion(
        (look, look),
        ceiling_channel=1,
        ceiling_max_step=0.03,
        channel_range=((0.25, 1.0), (0.45, 1.0)),
        channel_saturation=(1.0, 0.85),
        channel_hue_shift=(0.0, 0.08),
        channel_normalize=(normalizacion, normalizacion),
    )
    ctx = make_ctx(cfg=cfg)
    compositor = effect_modes.CompositionEffect(ComboEffect())
    anteriores: dict[int, base.Color] = {}
    picos: dict[int, float] = {}

    for frame in range(int(PERIOD * ctx.render_fps) + 1):
        canales = compositor.render(replace(ctx, now=ANCHOR + frame / ctx.render_fps))
        limitados, picos = sync._output_pipeline(
            canales, picos, anteriores, cfg, ctx.render_fps
        )
        if 1 in anteriores:
            assert abs(max(limitados[1]) - max(anteriores[1])) <= cfg.ceiling_max_step + 1e-12
        anteriores = limitados


def test_normalizar_despues_del_recorte_reabriria_el_salto_cenital():
    """El recorte debe ir ultimo: normalizar 0.53 lo volveria 0.79."""
    cfg = config_composicion(
        ceiling_channel=1,
        ceiling_max_step=0.03,
        channel_range=((0.25, 1.0), (0.45, 1.0)),
        channel_saturation=(1.0, 1.0),
        channel_hue_shift=(0.0, 0.0),
        channel_normalize=(0.0, 1.0),
    )
    limitado, _ = sync._output_pipeline(
        {1: (0.4, 0.2, 0.1)}, {1: 0.6}, {1: (0.5, 0.25, 0.125)}, cfg, 50.0
    )

    assert max(limitado[1]) <= 0.53 + 1e-12


def test_los_controles_por_canal_son_tuplas_en_yaml_y_entorno(tmp_path):
    """Falla si YAML y entorno dejan listas mutables o rangos desparejos."""
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        "effects:\n  channel_modes: [spectrum, idle]\n"
        "  channel_range: [[0.2, 0.8], [0.4, 1.0]]\n"
        "  channel_saturation: [0.9, 0.8]\n"
        "  channel_hue_shift: [0.0, 0.1]\n"
        "  channel_normalize: [0.2, 0.6]\n",
        encoding="utf-8",
    )
    desde_yaml = load_config(ruta).effects

    cfg = Config()
    apply_env_overrides(
        cfg,
        {
            "HUEBPM_EFFECTS_CHANNEL_MODES": '["spectrum", "idle"]',
            "HUEBPM_EFFECTS_CHANNEL_RANGE": "[[0.2, 0.8], [0.4, 1.0]]",
            "HUEBPM_EFFECTS_CHANNEL_SATURATION": "[0.9, 0.8]",
            "HUEBPM_EFFECTS_CHANNEL_HUE_SHIFT": "[0.0, 0.1]",
            "HUEBPM_EFFECTS_CHANNEL_NORMALIZE": "[0.2, 0.6]",
        },
    )

    esperado = ((0.2, 0.8), (0.4, 1.0))
    assert desde_yaml.channel_modes == cfg.effects.channel_modes == ("spectrum", "idle")
    assert desde_yaml.channel_range == cfg.effects.channel_range == esperado
    assert desde_yaml.channel_saturation == cfg.effects.channel_saturation == (0.9, 0.8)
    assert desde_yaml.channel_hue_shift == cfg.effects.channel_hue_shift == (0.0, 0.1)
    assert desde_yaml.channel_normalize == cfg.effects.channel_normalize == (0.2, 0.6)
