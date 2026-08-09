"""Los modos concretos. Todos caben en pocas lineas porque el trabajo duro
(fase del beat, normalizacion de bandas) ya esta hecho aguas arriba."""

from __future__ import annotations

from .base import (
    Channels,
    RenderContext,
    beat_envelope,
    blend,
    fill,
    harmony_color,
    harmony_mix,
    saturate,
    scale,
    spectrum_color,
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
        return fill(scale(ctx.cfg.idle_color, beat_envelope(ctx)), ctx.channel_count)


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
        return fill(
            scale(spectrum_color(ctx), beat_envelope(ctx)), ctx.channel_count
        )


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
        if not ctx.bar_locked:
            return fill(scale(spectrum_color(ctx), beat_envelope(ctx)), ctx.channel_count)

        paleta = ctx.cfg.phrase_palette
        compas = int(ctx.phrase_phase * len(paleta)) % len(paleta)
        color = saturate(paleta[compas], ctx.cfg.saturation_boost)
        return fill(scale(color, beat_envelope(ctx)), ctx.channel_count)


class HarmonyEffect:
    """Color por armonia, brillo por beat.

    Es el modo mas musical de los cinco: el color deja de responder al timbre
    de la mezcla y responde a que notas suenan, asi que se queda quieto
    mientras dura un acorde y se mueve cuando cambia. Los otros modos parpadean
    con cada golpe de bateria aunque la armonia no se haya movido.

    Cuando no hay contenido tonal —percusion sola, ruido— cae a color
    espectral. Inventarse un tono ahi produciria un color aleatorio que salta
    en cada golpe, que es peor que no seguir la armonia.

    El beat modula el brillo mucho menos que en los demas modos, y no es un
    detalle estetico: con la misma pulsacion que `combo`, el parpadeo domina la
    percepcion y el color pasa desapercibido, asi que los dos modos se ven
    identicos aunque el color sea distinto.
    """

    name = "harmony"

    def render(self, ctx: RenderContext) -> Channels:
        color = blend(spectrum_color(ctx), harmony_color(ctx), harmony_mix(ctx))
        profundidad = ctx.cfg.harmony_beat_depth
        brillo = 1.0 - profundidad + profundidad * beat_envelope(ctx)
        return fill(scale(color, brillo), ctx.channel_count)


EFFECTS = {
    e.name: e
    for e in (ComboEffect(), HarmonyEffect(), BarsEffect(),
              BeatFlashEffect(), SpectrumEffect(), IdleEffect())
}


def get_effect(name: str):  # noqa: ANN201
    try:
        return EFFECTS[name]
    except KeyError:
        raise ValueError(
            f"Modo desconocido {name!r}. Opciones: {', '.join(sorted(EFFECTS))}"
        ) from None
