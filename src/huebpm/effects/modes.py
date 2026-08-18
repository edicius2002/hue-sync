"""Los modos concretos. Todos caben en pocas lineas porque el trabajo duro
(fase del beat, normalizacion de bandas) ya esta hecho aguas arriba."""

from __future__ import annotations

from .base import (
    Channels,
    Color,
    Effect,
    RenderContext,
    apply_onset_flash,
    beat_envelope,
    blend,
    fill,
    gentle_brightness,
    harmony_color,
    harmony_mix,
    onset_accent,
    saturate,
    scale,
    spectrum_color,
    sustain_mix,
)


class IdleEffect:
    """Reposo: tenue y fijo. Nunca apagado del todo, para que se note que la
    app sigue viva y no parezca que se colgo."""

    name = "idle"

    def render(self, ctx: RenderContext) -> Channels:
        color = scale(ctx.cfg.idle_color, ctx.cfg.idle_brightness)
        return fill(color, ctx.channel_count)


class BeatFlashEffect:
    """Golpe de brillo en cada beat, color fijo del reposo."""

    name = "beat_flash"

    def render(self, ctx: RenderContext) -> Channels:
        brillo = min(1.0, beat_envelope(ctx) + onset_accent(ctx))
        color = apply_onset_flash(ctx, ctx.cfg.idle_color)
        return fill(scale(color, brillo), ctx.channel_count)


class SpectrumEffect:
    """Color por contenido espectral, brillo por energia. Sin ritmo."""

    name = "spectrum"

    def render(self, ctx: RenderContext) -> Channels:
        bands = list(ctx.state.bands) + [0.0, 0.0, 0.0]
        energy = max(bands[0], bands[1], bands[2])
        level = ctx.cfg.beat_floor + (1.0 - ctx.cfg.beat_floor) * energy
        return fill(scale(spectrum_color(ctx), level), ctx.channel_count)


class WashEffect:
    """Color fijo que respira con la energia, pensado para el techo.

    Dos matices distintos se suman a marron sobre las paredes de un cuarto
    pequeno. Reutilizar `idle_color` deja un unico color estable mientras la
    energia conserva el movimiento; es el intermedio entre `idle` plano y
    `spectrum`, que cambia de matiz. En render real a 50 fps tras el warmup,
    Billie llega a p99 0.52 y maximo 0.65 por frame; Summer llega a 0.31.
    Como el color es fijo, ``max(RGB) = nivel * max(idle_color)``: transmite
    el salto de energia entero, mientras la mezcla de color de `spectrum`
    amortigua su maximo RGB. Es el look mas abrupto y depende de `limit_slope`
    en la salida, no de una suavidad propia.

    En `summer.wav` se satura casi todo el tiempo (media de brillo crudo 0.925,
    minimo 0.825, CV 0.036), donde degenera visualmente en un `idle` brillante.
    Es una calibracion de `beat_floor`/energia, no una razon para cambiar el
    color fijo.
    """

    name = "wash"

    def render(self, ctx: RenderContext) -> Channels:
        bands = list(ctx.state.bands) + [0.0, 0.0, 0.0]
        energy = max(bands[0], bands[1], bands[2])
        level = ctx.cfg.beat_floor + (1.0 - ctx.cfg.beat_floor) * energy
        return fill(scale(ctx.cfg.idle_color, level), ctx.channel_count)


class ComboEffect:
    """El modo por defecto: color del espectro, brillo del beat.

    Separar las dos dimensiones es lo que hace que se lea como musica y no como
    un estrobo: el color dice *que* suena y el brillo dice *cuando*.
    """

    name = "combo"

    def render(self, ctx: RenderContext) -> Channels:
        brillo = min(1.0, beat_envelope(ctx) + onset_accent(ctx))
        color = apply_onset_flash(ctx, spectrum_color(ctx))
        return fill(scale(color, brillo), ctx.channel_count)


class BarsEffect:
    """Un color por compas dentro de la frase, brillo del beat.

    Es el modo que hace visible la estructura: la paleta avanza en el "1" de
    cada compas y vuelve a empezar cada frase, asi que se ve el 4x4 de la
    musica en vez de un parpadeo uniforme. Sin enganche de compas cae a color
    espectral, porque rotar una paleta en tiempos arbitrarios se ve peor que
    no rotarla.
    """

    name = "bars"

    def render(self, ctx: RenderContext) -> Channels:
        if ctx.bar_locked:
            paleta = ctx.cfg.phrase_palette
            compas = int(ctx.phrase_phase * len(paleta)) % len(paleta)
            base = saturate(paleta[compas], ctx.cfg.saturation_boost)
        else:
            base = spectrum_color(ctx)

        # El acento va fuera del if a proposito: el camino de respaldo se
        # quedaba sin onsets, que es exactamente el fallo que dejo `combo`
        # sin la feature entera.
        color = apply_onset_flash(ctx, base)
        brillo = min(1.0, beat_envelope(ctx) + onset_accent(ctx))
        return fill(scale(color, brillo), ctx.channel_count)


class HarmonyEffect:
    """Color por armonia, brillo por beat.

    Es el modo mas musical de los cinco: el color deja de responder al timbre
    de la mezcla y responde a que notas suenan, asi que se queda quieto
    mientras dura un acorde y se mueve cuando cambia. Los otros modos parpadean
    con cada golpe de bateria aunque la armonia no se haya movido.

    Cuando no hay contenido tonal —percusion sola, ruido— cae a color
    espectral. Inventarse un tono ahi produciria un color aleatorio que salta
    en cada golpe, que es peor que no seguir la armonia.

    Por defecto el brillo es **constante** y solo cambia el color: es la
    separacion limpia entre los dos modos, `combo` lleva el ritmo y `harmony`
    lleva la armonia. Subiendo `harmony_beat_depth` se le devuelve pulso, con
    la pendiente acotada para que no parpadee a tempos altos.
    """

    name = "harmony"

    def render(self, ctx: RenderContext) -> Channels:
        color = blend(spectrum_color(ctx), harmony_color(ctx), harmony_mix(ctx))
        brillo = gentle_brightness(
            ctx, ctx.cfg.harmony_beat_depth, ctx.cfg.harmony_max_step
        )
        return fill(scale(color, brillo), ctx.channel_count)


class SustainEffect:
    """Destello de beat que se vuelve brillo continuo con material sostenido.

    Pads, cuerdas, organo: el destello por golpe se lee como parpadeo porque
    el sonido no tiene transitorio. A 120 BPM y 50 fps la envolvente de pico
    salta 0.150 por frame; por encima de ~0.03 el ojo lo percibe como
    parpadeo. Se mezcla hacia `gentle_brightness` (profundidad 1, recortada
    por `sustain_max_step`), que ya acota esa pendiente a cualquier tempo.

    Con mezcla 0 el brillo es exactamente `beat_envelope`: degradacion segura
    mientras el detector no este cableado (sustain arranca a 0) y tambien
    cuando suena percusion o una cama de ruido.
    """

    name = "sustain"

    def render(self, ctx: RenderContext) -> Channels:
        mezcla = sustain_mix(ctx)
        destello = beat_envelope(ctx)
        continuo = gentle_brightness(ctx, 1.0, ctx.cfg.sustain_max_step)
        brillo = destello + (continuo - destello) * mezcla
        return fill(scale(spectrum_color(ctx), brillo), ctx.channel_count)


class CompositionEffect:
    """Compone un look y una ganancia por canal sin ser un look registrable.

    Un compositor dentro de ``EFFECTS`` podria componerse a si mismo y entrar
    en recursion. Solo se aceptan sus ocho looks reales; si la configuracion
    no describe el area entera se conserva el fallback para no dejar un canal
    mostrando su RGB viejo.
    """

    name = "composicion"

    def __init__(
        self,
        fallback: Effect,
        channel_modes: tuple[str, ...] | None = None,
        channel_gain: tuple[float, ...] | None = None,
    ) -> None:
        self.fallback = fallback
        self.channel_modes = channel_modes
        self.channel_gain = channel_gain

    def configuration(self, ctx: RenderContext) -> tuple[tuple[str, ...], tuple[float, ...]]:
        modes = self.channel_modes if self.channel_modes is not None else ctx.cfg.channel_modes
        gain = self.channel_gain if self.channel_gain is not None else ctx.cfg.channel_gain
        return modes, gain

    def is_valid(self, channel_count: int, cfg) -> bool:  # noqa: ANN001
        modes = self.channel_modes if self.channel_modes is not None else cfg.channel_modes
        gain = self.channel_gain if self.channel_gain is not None else cfg.channel_gain
        return (
            bool(modes)
            and len(modes) == channel_count
            and len(gain) == len(modes)
            and all(name in EFFECTS for name in modes)
            and all(0.0 <= value <= 1.0 for value in gain)
        )

    def render(self, ctx: RenderContext) -> Channels:
        modes, gain = self.configuration(ctx)
        if not self.is_valid(ctx.channel_count, ctx.cfg):
            return self.fallback.render(ctx)

        colores: dict[str, Color] = {}
        for name in modes:
            if name not in colores:
                colores[name] = EFFECTS[name].render(ctx)[0]
        return {
            channel: scale(colores[name], gain[channel])
            for channel, name in enumerate(modes)
        }


EFFECTS = {
    e.name: e
    for e in (ComboEffect(), HarmonyEffect(), BarsEffect(),
              BeatFlashEffect(), SpectrumEffect(), SustainEffect(), IdleEffect(),
              WashEffect())
}

LOOK_MAX_STEPS = {
    "beat_flash": 0.62,
    "bars": 0.62,
    "combo": 0.55,
    "harmony": 0.51,
    "spectrum": 0.50,
    "sustain": 0.31,
    "idle": 0.00,
    "wash": 0.65,
}
"""Maximos medidos de brillo por frame a 50 fps sobre audio real.

Sirven solo para avisar al arrancar: el recorte real vive en la salida y mide
cada frame, porque cualquier envolvente de audio puede superar esta referencia.
"""


def get_effect(name: str):  # noqa: ANN201
    try:
        return EFFECTS[name]
    except KeyError:
        raise ValueError(
            f"Modo desconocido {name!r}. Opciones: {', '.join(sorted(EFFECTS))}"
        ) from None
