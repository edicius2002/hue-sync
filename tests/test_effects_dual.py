"""Contrato del modo que separa pulso y armonia entre dos luces.

La pared lateral necesita marcar cuando cae el beat; el techo puede dejar ver
el acorde sin competir con ese pulso. El modo compone los dos efectos ya
probados, en vez de inventar una segunda cadena de color o de timing.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import ComboEffect, HarmonyEffect, get_effect
from huebpm.state import AudioState

ANCHOR = 100.0
PERIOD = 0.5


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


def test_dual_techo_varia_menos_que_la_pared_con_el_beat():
    """A 120 BPM/50 fps, pared varia 0.672452180295 y techo 0.000000000000."""
    ctx = make_ctx()
    dual = get_effect("dual")
    pared = []
    techo = []
    for phase in np.arange(0.0, 1.001, 0.02):
        colores = dual.render(replace(ctx, now=ANCHOR + float(phase) * PERIOD))
        pared.append(max(colores[ctx.cfg.wall_channel]))
        techo.append(max(colores[ctx.cfg.ceiling_channel]))

    variacion_pared = max(pared) - min(pared)
    variacion_techo = max(techo) - min(techo)
    assert variacion_techo <= variacion_pared


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

    assert colores_intercambiados[intercambiado.cfg.wall_channel] == colores_normales[
        normal.cfg.wall_channel
    ]
    assert colores_intercambiados[intercambiado.cfg.ceiling_channel] == colores_normales[
        normal.cfg.ceiling_channel
    ]
