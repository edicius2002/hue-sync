"""Los modos concretos. Todos caben en pocas lineas porque el trabajo duro
(fase del beat, normalizacion de bandas) ya esta hecho aguas arriba."""

from __future__ import annotations

from .base import (
    Channels,
    RenderContext,
    beat_envelope,
    fill,
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


EFFECTS = {
    e.name: e
    for e in (ComboEffect(), BeatFlashEffect(), SpectrumEffect(), IdleEffect())
}


def get_effect(name: str):  # noqa: ANN201
    try:
        return EFFECTS[name]
    except KeyError:
        raise ValueError(
            f"Modo desconocido {name!r}. Opciones: {', '.join(sorted(EFFECTS))}"
        ) from None
