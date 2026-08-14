"""Los modos concretos. Todos caben en pocas lineas porque el trabajo duro
(fase del beat, normalizacion de bandas) ya esta hecho aguas arriba."""

from __future__ import annotations

from .base import (
    Channels,
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
    por `harmony_max_step`), que ya acota esa pendiente a cualquier tempo.

    Con mezcla 0 el brillo es exactamente `beat_envelope`: degradacion segura
    mientras el detector no este cableado (sustain arranca a 0) y tambien
    cuando suena percusion o una cama de ruido.
    """

    name = "sustain"

    def render(self, ctx: RenderContext) -> Channels:
        mezcla = sustain_mix(ctx)
        destello = beat_envelope(ctx)
        continuo = gentle_brightness(ctx, 1.0, ctx.cfg.harmony_max_step)
        brillo = destello + (continuo - destello) * mezcla
        return fill(scale(spectrum_color(ctx), brillo), ctx.channel_count)


EFFECTS = {
    e.name: e
    for e in (ComboEffect(), HarmonyEffect(), BarsEffect(),
              BeatFlashEffect(), SpectrumEffect(), IdleEffect(), SustainEffect())
}


def get_effect(name: str):  # noqa: ANN201
    try:
        return EFFECTS[name]
    except KeyError:
        raise ValueError(
            f"Modo desconocido {name!r}. Opciones: {', '.join(sorted(EFFECTS))}"
        ) from None
