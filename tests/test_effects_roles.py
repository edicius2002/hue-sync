"""Contrato del modo que reparte roles musicales entre varios canales.

Cada canal recibe un efecto por una lista ordenada. Eso mantiene separado el
pulso visible de la armonia estable sin asumir que todas las entertainment
areas tienen exactamente las dos luces del cuarto de pruebas.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import Config, EffectsConfig, apply_env_overrides, load_config
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import (
    ComboEffect,
    HarmonyEffect,
    SpectrumEffect,
    SustainEffect,
    get_effect,
)
from huebpm.state import AudioState

ANCHOR = 100.0
PERIOD = 0.5
MAX_STEP_ARMONIA = 0.03
"""Por encima de este salto por frame a 50 fps el ojo lee parpadeo."""


def config_con_roles(roles: tuple[str, ...], **cambios) -> EffectsConfig:
    cfg = EffectsConfig(**cambios)
    cfg.channel_roles = roles
    return cfg


def make_ctx(
    roles: tuple[str, ...] = ("pulso", "armonia"),
    *,
    channel_count: int | None = None,
    cfg: EffectsConfig | None = None,
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
        channel_count=channel_count if channel_count is not None else len(roles),
        cfg=cfg or config_con_roles(roles),
        render_fps=50.0,
    )


def saltos_de_canal(ctx: RenderContext, channel: int) -> np.ndarray:
    """Mide el cambio que vera un canal entre frames reales de render."""
    frames = int(round(PERIOD * ctx.render_fps))
    effect = get_effect("roles")
    brillos = np.array(
        [
            max(effect.render(replace(ctx, now=ANCHOR + frame / ctx.render_fps))[channel])
            for frame in range(frames + 1)
        ]
    )
    return np.abs(np.diff(brillos))


def test_roles_se_registra_como_modo():
    assert get_effect("roles").name == "roles"


def test_roles_por_defecto_conserva_el_reparto_de_dual():
    """Dos canales pulso/armonia deben quedar bit a bit como el dual revisado."""
    ctx = make_ctx()
    esperado = {
        0: ComboEffect().render(ctx)[0],
        1: HarmonyEffect().render(ctx)[0],
    }
    assert get_effect("roles").render(ctx) == esperado


def test_roles_usa_la_tupla_por_defecto_de_effects_config():
    """El modo no necesita un helper que fuerce la pareja pulso/armonia."""
    cfg = EffectsConfig()
    ctx = make_ctx(channel_count=2, cfg=cfg)
    assert cfg.channel_roles == ("pulso", "armonia")
    assert get_effect("roles").render(ctx) == {
        0: ComboEffect().render(ctx)[0],
        1: HarmonyEffect().render(ctx)[0],
    }


def test_roles_reparte_los_cuatro_efectos_por_indice():
    roles = ("pulso", "armonia", "espectro", "sostenido")
    ctx = make_ctx(roles)
    esperado = {
        0: ComboEffect().render(ctx)[0],
        1: HarmonyEffect().render(ctx)[0],
        2: SpectrumEffect().render(ctx)[0],
        3: SustainEffect().render(ctx)[0],
    }
    assert get_effect("roles").render(ctx) == esperado


@pytest.mark.parametrize(
    "roles",
    [
        ("pulso", "armonia"),
        ("armonia", "pulso", "espectro"),
        ("sostenido", "armonia", "pulso", "armonia"),
    ],
)
def test_todo_canal_armonia_respeta_el_limite_antiparpadeo(roles):
    """A 120 BPM/50 fps, `armonia` no supera 0.03 aunque cambie de canal."""
    cfg = config_con_roles(roles, harmony_beat_depth=1.0)
    ctx = make_ctx(roles, cfg=cfg)
    for channel, role in enumerate(roles):
        if role == "armonia":
            assert saltos_de_canal(ctx, channel).max() <= MAX_STEP_ARMONIA


def test_armonia_admite_respiracion_suave():
    """Con profundidad 0.10, 0.012509 por frame sigue bajo la cota visual."""
    roles = ("pulso", "armonia", "espectro")
    ctx = make_ctx(roles, cfg=config_con_roles(roles, harmony_beat_depth=0.10))
    assert saltos_de_canal(ctx, 1).max() <= MAX_STEP_ARMONIA


@pytest.mark.parametrize("role", ("pulso", "sostenido"))
def test_roles_ritmicos_superan_el_limite_antiparpadeo(role):
    """A 120 BPM/50 fps, pulso y sostenido sin mezcla saltan 0.336 por frame."""
    roles = ("armonia", role, "espectro")
    assert saltos_de_canal(make_ctx(roles), 1).max() > MAX_STEP_ARMONIA


@pytest.mark.parametrize(
    "roles,channel_count",
    [
        (("pulso",), 2),
        ((), 2),
        (("roles", "roles"), 2),
        (("pulso", "desconocido"), 2),
    ],
)
def test_roles_invalidos_degradan_a_combo(roles, channel_count):
    """Una lista incompleta, vacia, recursiva o desconocida no rompe el loop."""
    ctx = make_ctx(roles, channel_count=channel_count)
    assert get_effect("roles").render(ctx) == ComboEffect().render(ctx)


def test_channel_roles_es_tupla_tanto_en_yaml_como_en_entorno(tmp_path):
    """El override no puede dejar lista mutable donde YAML entrega una tupla."""
    ruta = tmp_path / "config.yaml"
    ruta.write_text("effects:\n  channel_roles: [espectro, pulso, armonia]\n", encoding="utf-8")
    desde_yaml = load_config(ruta).effects.channel_roles

    cfg = Config()
    apply_env_overrides(
        cfg,
        {"HUEBPM_EFFECTS_CHANNEL_ROLES": '["espectro", "pulso", "armonia"]'},
    )
    desde_entorno = cfg.effects.channel_roles

    assert desde_yaml == desde_entorno == ("espectro", "pulso", "armonia")
    assert isinstance(desde_yaml, tuple)
    assert isinstance(desde_entorno, tuple)
