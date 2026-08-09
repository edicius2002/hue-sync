"""Efectos: funciones puras del reloj y del estado de audio.

Un efecto no guarda estado propio ni sabe nada de DTLS ni de audio: recibe un
contexto y devuelve colores. Eso lo hace trivial de probar sin bridge y sin
tarjeta de sonido, y anadir un modo nuevo es un archivo.

La envolvente de brillo se calcula a partir de la *fase* del beat, no de
eventos "hubo un beat". Es la diferencia entre poder subir el brillo hacia el
golpe y solo poder reaccionar despues.
"""

from __future__ import annotations

import colorsys
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

    bar_phase: float = 0.0
    """Posicion dentro del compas, 0..1. 0 es el downbeat."""
    phrase_phase: float = 0.0
    """Posicion dentro de la frase de `beats_per_phrase`, 0..1."""
    beat_in_bar: int = 0
    """Que tiempo del compas es este. 0 es el "1"."""
    bar_locked: bool = False
    """False mientras no haya evidencia suficiente de donde cae el compas. Los
    efectos deben degradar a tratar todos los beats por igual, no inventarse
    un downbeat que no esta."""


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

    # Acento del downbeat: el "1" pega mas fuerte que el resto. Es lo que
    # convierte una sucesion de destellos iguales en algo con metrica.
    if ctx.bar_locked and ctx.beat_in_bar != 0:
        level *= 1.0 - cfg.downbeat_accent

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


def harmony_color(ctx: RenderContext) -> Color:
    """Color derivado de la posicion en el circulo cromatico."""
    # La saturacion sigue a la tonalidad: cuanto mas clara es la armonia, mas
    # puro el color. Un pasaje ambiguo se ve lavado en vez de mentir.
    sat = min(1.0, ctx.cfg.harmony_saturation * ctx.state.tonality / 0.08)
    return colorsys.hsv_to_rgb(ctx.state.chroma_hue, sat, 1.0)


def harmony_mix(ctx: RenderContext) -> float:
    """Cuanto fiarse de la armonia, 0..1.

    Es una rampa y no un umbral duro por una razon medida: con un corte seco,
    cruzarlo produce un salto de color de casi el rango entero (0.99 sobre 1.0
    de distancia RGB), que se ve como un fogonazo cuando la tonalidad ronda el
    limite. Mezclando progresivamente hacia el color espectral, el paso es
    invisible.
    """
    minimo = ctx.cfg.harmony_min_tonality
    rango = max(1e-6, ctx.cfg.harmony_full_tonality - minimo)
    return max(0.0, min(1.0, (ctx.state.tonality - minimo) / rango))


def blend(a: Color, b: Color, t: float) -> Color:
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def scale(color: Color, factor: float) -> Color:
    return (color[0] * factor, color[1] * factor, color[2] * factor)


def fill(color: Color, count: int) -> Channels:
    return {i: color for i in range(max(1, count))}
