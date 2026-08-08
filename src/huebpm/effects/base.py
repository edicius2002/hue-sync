"""Efectos: funciones puras del reloj y del estado de audio.

Un efecto no guarda estado propio ni sabe nada de DTLS ni de audio: recibe un
contexto y devuelve colores. Eso lo hace trivial de probar sin bridge y sin
tarjeta de sonido, y anadir un modo nuevo es un archivo.

La envolvente de brillo se calcula a partir de la *fase* del beat, no de
eventos "hubo un beat". Es la diferencia entre poder subir el brillo hacia el
golpe y solo poder reaccionar despues.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from ..analysis.beatclock import BeatClock
from ..config import EffectsConfig
from ..state import AudioState

Color = tuple[float, float, float]
Channels = dict[int, Color]


@dataclass(frozen=True)
class RenderContext:
    now: float
    """Tiempo de pared YA compensado por latencia: es el instante en que la luz
    va a mostrar esto, no aquel en que se calcula."""
    state: AudioState
    clock: BeatClock
    channel_count: int
    cfg: EffectsConfig


class Effect(Protocol):
    name: str

    def render(self, ctx: RenderContext) -> Channels: ...


def beat_envelope(ctx: RenderContext) -> float:
    """Brillo 0..1 en funcion de la posicion dentro del beat.

    Sube durante la fraccion `beat_attack` ANTERIOR al golpe y decae despues.
    Sin enganche devuelve un valor fijo, que es lo que evita que la luz se
    quede a oscuras en pasajes sin pulso claro.
    """
    cfg = ctx.cfg
    if not ctx.clock.locked:
        return cfg.beat_floor

    phase = ctx.clock.phase(ctx.now)  # 0.0 justo en el golpe
    attack = max(1e-3, cfg.beat_attack)

    if phase > 1.0 - attack:
        # Tramo de anticipacion: rampa hacia el golpe que aun no ha sonado.
        # Arranca desde donde iba la caida, no desde cero, o habria un escalon
        # a la baja justo antes de subir.
        rise = (phase - (1.0 - attack)) / attack
        base = math.exp(-cfg.beat_decay * (1.0 - attack))
        level = base + (1.0 - base) * rise
    else:
        level = math.exp(-cfg.beat_decay * phase)

    return cfg.beat_floor + (1.0 - cfg.beat_floor) * level


def spectrum_color(ctx: RenderContext) -> Color:
    """Mezcla graves/medios/agudos en un color, por peso de energia."""
    cfg = ctx.cfg
    bands = list(ctx.state.bands) + [0.0, 0.0, 0.0]
    bass, mid, treble = bands[0], bands[1], bands[2]
    total = bass + mid + treble
    if total < 1e-6:
        return cfg.idle_color

    r = (cfg.bass_color[0] * bass + cfg.mid_color[0] * mid + cfg.treble_color[0] * treble) / total
    g = (cfg.bass_color[1] * bass + cfg.mid_color[1] * mid + cfg.treble_color[1] * treble) / total
    b = (cfg.bass_color[2] * bass + cfg.mid_color[2] * mid + cfg.treble_color[2] * treble) / total
    return saturate((r, g, b), cfg.saturation_boost)


def saturate(color: Color, boost: float) -> Color:
    """Aleja el color del gris. Las luces Hue lavan los tonos mezclados."""
    if boost <= 1.0:
        return color
    mean = sum(color) / 3.0
    return tuple(  # type: ignore[return-value]
        max(0.0, min(1.0, mean + (c - mean) * boost)) for c in color
    )


def scale(color: Color, factor: float) -> Color:
    return (color[0] * factor, color[1] * factor, color[2] * factor)


def fill(color: Color, count: int) -> Channels:
    return {i: color for i in range(max(1, count))}
