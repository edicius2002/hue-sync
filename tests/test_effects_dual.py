"""Contrato del modo que separa pulso y armonia entre dos luces.

La pared lateral necesita marcar cuando cae el beat; el techo puede dejar ver
el acorde sin competir con ese pulso. El modo compone los dos efectos ya
probados, en vez de inventar una segunda cadena de color o de timing.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import ComboEffect, HarmonyEffect, get_effect
from huebpm.state import AudioState

ANCHOR = 100.0
PERIOD = 0.5
MAX_STEP_TECHO = 0.03
"""Por encima de este salto por frame a 50 fps el ojo lee parpadeo."""


def make_ctx(phase: float = 0.0, *, channel_count: int = 2, cfg: EffectsConfig | None = None):
    clock = BeatClock()
    clock.update(
        TempoEstimate(bpm=120.0, period=PERIOD, last_beat_time=ANCHOR, confidence=1.0),
        ANCHOR,
    )
    return RenderContext(
        now=ANCHOR + phase * PERIOD,
        state=AudioState(bands=np.array((0.9, 0.3, 0.1)), locked=True, tonality=0.5),
        clock=clock,
        channel_count=channel_count,
        cfg=cfg or EffectsConfig(),
        render_fps=50.0,
    )


def test_dual_se_registra_como_modo():
    """Un nombre no registrado deja al CLI sin forma de seleccionar el modo."""
    assert get_effect("dual").name == "dual"


def test_dual_entrega_un_color_por_rol():
    """Dos luces tienen dos roles: pared de pulso y techo de armonia."""
    ctx = make_ctx()
    obtenido = get_effect("dual").render(ctx)
    assert set(obtenido) == {ctx.cfg.wall_channel, ctx.cfg.ceiling_channel}


def test_dual_pared_es_exactamente_combo():
    """Cambiar el compositor no puede cambiar el pulso historico de la pared."""
    ctx = make_ctx(0.5)
    obtenido = get_effect("dual").render(ctx)
    assert obtenido[ctx.cfg.wall_channel] == ComboEffect().render(ctx)[0]


def test_dual_techo_es_exactamente_harmony():
    """El techo recibe el color y brillo que ya define el modo armonico."""
    ctx = make_ctx(0.5)
    obtenido = get_effect("dual").render(ctx)
    assert obtenido[ctx.cfg.ceiling_channel] == HarmonyEffect().render(ctx)[0]


def test_dual_con_una_luz_degrada_a_combo_sin_cambiar_el_dict():
    """En un area generica de un canal se conserva el comportamiento historico."""
    ctx = make_ctx(channel_count=1)
    assert get_effect("dual").render(ctx) == ComboEffect().render(ctx)


def saltos_de_techo(ctx: RenderContext) -> np.ndarray:
    """Mide el cambio que vera la luz entre frames reales de render."""
    frames = int(round(PERIOD * ctx.render_fps))
    dual = get_effect("dual")
    brillos = np.array(
        [
            max(
                dual.render(replace(ctx, now=ANCHOR + frame / ctx.render_fps))[
                    ctx.cfg.ceiling_channel
                ]
            )
            for frame in range(frames + 1)
        ]
    )
    return np.abs(np.diff(brillos))


def test_dual_techo_no_supera_el_salto_por_frame():
    """A 120 BPM/50 fps pared salta 0.336 y techo quieto 0.000000.

    Se prueba profundidad 1 para que afinar `harmony_max_step` no pueda
    desactivar el limite: el techo debe seguir sin superar 0.03 por frame.
    """
    ctx = make_ctx(cfg=EffectsConfig(harmony_beat_depth=1.0))
    assert saltos_de_techo(ctx).max() <= MAX_STEP_TECHO


def test_dual_techo_admite_respiracion_suave():
    """Con profundidad 0.10, 0.012509 por frame sigue bajo la cota visual."""
    ctx = make_ctx(cfg=EffectsConfig(harmony_beat_depth=0.10))
    assert saltos_de_techo(ctx).max() <= MAX_STEP_TECHO


def test_dual_respeta_el_orden_configurado_de_los_roles():
    """Los IDs son orden de insercion, asi que invertirlos mueve ambos roles."""
    normal = make_ctx()
    intercambiado = make_ctx(
        cfg=EffectsConfig(
            wall_channel=normal.cfg.ceiling_channel,
            ceiling_channel=normal.cfg.wall_channel,
        )
    )
    dual = get_effect("dual")
    colores_normales = dual.render(normal)
    colores_intercambiados = dual.render(intercambiado)

    assert colores_normales[0] == ComboEffect().render(normal)[0]
    assert colores_normales[1] == HarmonyEffect().render(normal)[0]
    assert colores_intercambiados[1] == ComboEffect().render(intercambiado)[0]
    assert colores_intercambiados[0] == HarmonyEffect().render(intercambiado)[0]


def test_dual_con_roles_en_el_mismo_canal_degrada_a_combo():
    """Dos roles en una clave colapsarian el dict y dejarian una luz sin orden."""
    ctx = make_ctx(cfg=EffectsConfig(wall_channel=0, ceiling_channel=0))
    assert get_effect("dual").render(ctx) == ComboEffect().render(ctx)


def test_dual_con_mas_de_dos_luces_degrada_a_combo():
    """`dual` solo sabe repartir dos roles; no deja canales extra con color viejo."""
    ctx = make_ctx(channel_count=3)
    assert get_effect("dual").render(ctx) == ComboEffect().render(ctx)


@pytest.mark.parametrize("wall,ceiling", [(5, 1), (-1, 0)])
def test_dual_con_ids_fuera_del_area_degrada_a_combo(wall, ceiling):
    """Un ID invalido no puede omitir una luz y dejarle el color anterior."""
    ctx = make_ctx(cfg=EffectsConfig(wall_channel=wall, ceiling_channel=ceiling))
    assert get_effect("dual").render(ctx) == ComboEffect().render(ctx)
