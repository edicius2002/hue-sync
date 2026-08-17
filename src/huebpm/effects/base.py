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
    render_fps: float = 50.0
    """Necesario para acotar la pendiente del brillo: cuanto avanza la fase
    entre dos frames depende del tempo, asi que la suavidad percibida tambien."""
    now_real: float | None = None
    """Tiempo de pared SIN compensar, para lo que es reactivo y no predictivo.

    `now` va adelantado por `latency_compensation_ms` porque el reloj de beat
    predice el futuro. Un onset no se puede predecir: cuando se detecta, ya
    ocurrio. Evaluarlo en el futuro solo lo muestra ya apagado."""
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


def smooth_envelope(ctx: RenderContext) -> float:
    """Envolvente sinusoidal: 1.0 en el beat, 0.0 en el contratiempo.

    Alternativa a `beat_envelope` para los modos donde el color es lo que
    importa. La envolvente normal es un pico agudo con caida exponencial, y los
    picos agudos se leen como destellos aunque el rango de brillo sea pequeno.

    Medido a 120 BPM y 50 fps, el brillo salta hasta 0.150 por frame con la
    envolvente de pico contra 0.044 con el coseno, y eso **con mas rango de
    brillo**. Por encima de unos 0.03 por frame el ojo lo percibe como
    parpadeo. Lo que hace falta cambiar es la forma, no la profundidad.
    """
    if not ctx.clock.locked:
        return 1.0
    return 0.5 + 0.5 * math.cos(2.0 * math.pi * ctx.clock.phase(ctx.now))


def onset_accent(ctx: RenderContext) -> float:
    """Golpe de brillo extra que decae tras un onset fuera de tiempo, 0..1.

    Es funcion pura del tiempo transcurrido porque el estado publica el
    instante del golpe y no un nivel ya calculado. Asi el efecto no guarda nada
    y sigue siendo testeable sin motor.
    """
    if ctx.cfg.onset_accent <= 0.0:
        return 0.0
    # Sin compensar: el beat se predice, un golpe suelto no. Mirando el futuro
    # el acento llegaria ya decaido, que es justo lo contrario de lo que hace
    # falta. Con `onset_decay` de 90 ms y 120 ms de compensacion, se perderia
    # el 74% del golpe antes de mostrarlo.
    ahora = ctx.now_real if ctx.now_real is not None else ctx.now
    transcurrido = ahora - ctx.state.last_onset_time
    if transcurrido < 0.0 or transcurrido > 8.0 * ctx.cfg.onset_decay:
        return 0.0
    caida = math.exp(-transcurrido / max(1e-6, ctx.cfg.onset_decay))
    return ctx.cfg.onset_accent * ctx.state.last_onset_strength * caida


def apply_onset_flash(ctx: RenderContext, color: Color) -> Color:
    """Blanquea el color en proporcion al acento del onset.

    Con una sola luz, el brillo es un canal pobre para senalar un golpe: cerca
    de un beat la envolvente ya esta arriba y sumar acento se satura sin que se
    note. El color si esta libre, y un blanqueo momentaneo se lee como un
    impacto claramente distinto del pulso.
    """
    fuerza = onset_accent(ctx)
    if fuerza <= 0.0 or ctx.cfg.onset_flash <= 0.0:
        return color
    mezcla = min(1.0, fuerza * ctx.cfg.onset_flash / max(1e-6, ctx.cfg.onset_accent))
    return blend(color, (1.0, 1.0, 1.0), mezcla)


def gentle_brightness(ctx: RenderContext, depth: float, max_step: float) -> float:
    """Brillo sinusoidal con la pendiente acotada, independiente del tempo.

    La suavidad percibida no depende de cuanto varia el brillo sino de cuanto
    varia **entre frames consecutivos**, y eso escala con el tempo: la fase
    avanza (BPM/60)/fps por frame, asi que un ajuste comodo a 120 BPM parpadea
    a 174. Aqui se recorta la profundidad para que el salto maximo nunca supere
    `max_step`, lo que da la misma sensacion a cualquier tempo.

    La pendiente maxima de 0.5+0.5*cos(2*pi*f) es pi, en el contratiempo.
    """
    if depth <= 0.0 or not ctx.clock.locked:
        return 1.0

    periodo = ctx.clock.period or 0.5
    avance_de_fase = 1.0 / (periodo * ctx.render_fps)
    limite = max_step / max(1e-9, math.pi * avance_de_fase)
    depth = min(depth, limite)

    return 1.0 - depth + depth * smooth_envelope(ctx)


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


def sustain_mix(ctx: RenderContext) -> float:
    """Cuanto cruzar de destello a brillo continuo, 0..1.

    Producto de dos rampas, no min(). min() crea un pliegue donde cambia la
    restriccion activa, y las transiciones duras aqui se ven como fogonazo:
    la misma razon, medida, que documenta `harmony_mix`. El producto es un
    AND: si cualquiera de las dos esta baja, la mezcla cae a 0 y el modo
    degrada a envolvente de beat.

    La rampa de tonalidad es la que excluye camas de ruido y aplausos: el
    detector publica sustain crudo, sin filtrar, y filtrarlo es trabajo de
    este efecto.
    """
    cfg = ctx.cfg
    rango_s = max(1e-6, cfg.sustain_full - cfg.sustain_min)
    rango_t = max(1e-6, cfg.sustain_full_tonality - cfg.sustain_min_tonality)
    sostenido = max(0.0, min(1.0, (ctx.state.sustain - cfg.sustain_min) / rango_s))
    tonalidad = max(
        0.0, min(1.0, (ctx.state.tonality - cfg.sustain_min_tonality) / rango_t)
    )
    return sostenido * tonalidad


def blend(a: Color, b: Color, t: float) -> Color:
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def scale(color: Color, factor: float) -> Color:
    return (color[0] * factor, color[1] * factor, color[2] * factor)


def limit_slope(
    previo: float | None, nuevo: Channels, canal: int, max_step: float
) -> Channels:
    """Acota el brillo de un canal sin mover su matiz.

    La pendiente se mide sobre ``max(R, G, B)`` porque limitar componentes por
    separado cambia la proporcion entre ellas y por tanto el color. El estado
    del frame anterior vive en el loop de salida: los efectos siguen puros y
    el primer frame no se toca porque aun no existe una pendiente que limitar.
    """
    if previo is None or canal not in nuevo:
        return nuevo

    color = nuevo[canal]
    brillo = max(color)
    limitado = min(previo + max_step, max(previo - max_step, brillo))
    if brillo <= 1e-9:
        return nuevo

    canales = nuevo.copy()
    canales[canal] = scale(color, limitado / brillo)
    return canales


def fill(color: Color, count: int) -> Channels:
    return {i: color for i in range(max(1, count))}
