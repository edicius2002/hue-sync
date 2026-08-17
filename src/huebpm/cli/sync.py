"""El comando principal: audio del sistema -> BPM -> luces.

Aqui se juntan las dos mitades del proyecto. El punto de todo el diseno es
esta linea del loop:

    lookahead = now + latency_compensation

El efecto se evalua en el futuro, no en el presente, asi que el comando sale
del PC *antes* del beat y la luz enciende justo en el golpe. Un sistema
reactivo no puede hacerlo: para cuando detecta el beat, ya llega tarde por la
suma de captura, analisis, DTLS y el salto Zigbee.
"""

from __future__ import annotations

import sys
import time

from ..audio.capture import LoopbackCapture, resolve_device
from ..config import Config, load_hue_credentials
from ..effects.base import Channels, RenderContext, limit_slope
from ..effects.modes import LOOK_MAX_STEPS, CompositionEffect, IdleEffect, get_effect
from ..engine import AnalysisEngine, LiveAnalyzer
from ..hue.backends import StreamError
from ..hue.client import EntertainmentSession
from ..hue.rest import BridgeError
from ..timing import RateLimiter, TimerResolution


def run_sync(
    cfg: Config,
    duration: float | None = None,
    mode: str | None = None,
    area_id: str | None = None,
    dry_run: bool = False,
) -> int:
    try:
        effect = get_effect(mode or cfg.effects.mode)
    except ValueError as exc:
        print(exc)
        return 1
    idle_effect = IdleEffect()

    device = resolve_device(cfg.audio.device_index, cfg.audio.device_name)
    capture = LoopbackCapture(
        device=device,
        blocksize=cfg.audio.blocksize,
        buffer_seconds=cfg.audio.buffer_seconds,
    )
    engine = AnalysisEngine(device.samplerate, cfg.analysis)
    analyzer = LiveAnalyzer(capture, engine)

    session = None
    channel_count = 1
    if not dry_run:
        try:
            creds = load_hue_credentials()
        except (FileNotFoundError, ValueError) as exc:
            print(exc)
            return 1
        area = area_id or creds.entertainment_area_id
        if not area:
            print("Falta entertainment_area_id en hue_config.json (o usa --area).")
            return 1
        session = EntertainmentSession(
            creds.bridge_ip, creds.username, creds.clientkey, area
        )
        try:
            session.start()
        except (BridgeError, StreamError) as exc:
            print(f"\n{exc}\n")
            print("Cierra Hue Sync si esta abierto: compite por la misma area.")
            return 1
        channel_count = session.channel_count or 1

    channel_modes = (mode,) * channel_count if mode else cfg.effects.channel_modes
    channel_gain = (1.0,) * channel_count if mode else cfg.effects.channel_gain
    composition = CompositionEffect(effect, channel_modes, channel_gain)
    composition_valid = composition.is_valid(channel_count, cfg.effects)

    comp = cfg.render.latency_compensation_ms / 1000.0
    print(f"Audio:  [{device.index}] {device.name} @ {device.samplerate} Hz")
    print(f"Luces:  {'(dry-run, sin bridge)' if dry_run else f'{channel_count} canal(es)'}")
    print(f"Modo:   {effect.name}   render {cfg.render.fps:.0f} Hz   "
          f"compensacion {cfg.render.latency_compensation_ms:.0f} ms")
    if not composition_valid:
        print(
            "AVISO: composicion invalida: esperaba "
            f"{channel_count} modos y la misma cantidad de ganancias; encontro "
            f"channel_modes={channel_modes!r}, channel_gain={channel_gain!r}. "
            f"Se usara mode `{effect.name}` en todos los canales."
        )
    elif cfg.effects.ceiling_clamp and cfg.effects.ceiling_channel is not None:
        ceiling = cfg.effects.ceiling_channel
        if 0 <= ceiling < channel_count:
            look = channel_modes[ceiling]
            salto = LOOK_MAX_STEPS[look]
            if salto > cfg.effects.ceiling_max_step:
                print(
                    f"AVISO: canal {ceiling} (cenital) con `{look}`, que salta hasta "
                    f"{salto:.2f}/frame sobre audio real. Se recorta a "
                    f"{cfg.effects.ceiling_max_step:.2f}. Para verlo sin recortar: "
                    "ceiling_clamp: false"
                )
    if cfg.env_overrides:
        # Se muestran a proposito: un ajuste que crees activo y no lo esta, o
        # uno que sigue puesto de una prueba anterior, cuesta horas.
        print(f"Entorno: {'   '.join(cfg.env_overrides)}")
    print("Ctrl-C para salir.\n")

    limiter = RateLimiter(cfg.render.fps)
    started = time.perf_counter()
    sent = failed = 0
    next_status = 0.0
    previous_brightness: dict[int, float] = {}

    capture.start()
    analyzer.start()
    try:
        with TimerResolution(1):
            while True:
                now = limiter.tick()
                if duration and now - started > duration:
                    break

                state = engine.state
                # El efecto se evalua en el instante en que la luz mostrara
                # esto, no en el que se calcula.
                lookahead = now + comp
                ctx = _context(engine, state, lookahead, channel_count, cfg, now_real=now)
                active = idle_effect if state.silent else composition
                channels = active.render(ctx)
                if state.silent:
                    # `idle` es plano: al volver a sonar no hay pendiente que
                    # heredar de un frame que ya no representaba la musica.
                    previous_brightness.clear()
                else:
                    channels = _limit_ceiling(channels, previous_brightness, cfg.effects)
                    previous_brightness = {
                        channel: max(color) for channel, color in channels.items()
                    }

                if session is not None:
                    if session.send(channels):
                        sent += 1
                    else:
                        failed += 1
                    session.keepalive()

                if now >= next_status:
                    next_status = now + 0.1
                    _status(state, engine, channels, sent, failed, limiter,
                            active.name, lookahead)
    except KeyboardInterrupt:
        pass
    finally:
        print()
        analyzer.stop()
        capture.stop()
        if session is not None:
            session.stop()
            print("Sesion de streaming cerrada.")

    if session is not None:
        print(f"Paquetes: {sent} enviados, {failed} fallidos")
    print(f"Jitter del loop: media {limiter.jitter.mean_ms:.2f} ms, "
          f"max {limiter.jitter.max_ms:.2f} ms")
    return 0


def _limit_ceiling(
    channels: Channels, previous_brightness: dict[int, float], cfg
) -> Channels:  # noqa: ANN001
    """Aplica la proteccion de salida solo al canal cenital declarado."""
    ceiling = cfg.ceiling_channel
    if not cfg.ceiling_clamp or ceiling is None:
        return channels
    return limit_slope(
        previous_brightness.get(ceiling), channels, ceiling, cfg.ceiling_max_step
    )


def _context(engine, state, now, channel_count, cfg, now_real=None) -> RenderContext:  # noqa: ANN001
    """Construye el contexto del efecto, incluyendo la metrica del compas.

    Se calcula aqui y no dentro de cada efecto para que los efectos sigan
    siendo funciones puras de datos ya resueltos.
    """
    bars, clock = engine.bars, engine.clock
    index = clock.beat_index(now)
    if index is None or not bars.locked:
        return RenderContext(
            now=now, state=state, clock=clock,
            channel_count=channel_count, cfg=cfg.effects,
            render_fps=cfg.render.fps, now_real=now_real,
        )

    beat_phase = clock.phase(now)
    return RenderContext(
        now=now, state=state, clock=clock,
        channel_count=channel_count, cfg=cfg.effects,
        bar_phase=bars.bar_phase(index, beat_phase),
        phrase_phase=bars.phrase_phase(index, beat_phase),
        beat_in_bar=bars.beat_in_bar(index),
        bar_locked=True,
        render_fps=cfg.render.fps,
        now_real=now_real,
    )


def _status(state, engine, channels, sent, failed, limiter, mode, now) -> None:  # noqa: ANN001
    bpm = f"{state.bpm:6.1f}" if state.bpm else "  --  "
    r, g, b = next(iter(channels.values()))
    niveles = "".join(
        "#" * int(round(v * 8)) + "." * (8 - int(round(v * 8)))
        for v in (list(state.bands) + [0, 0, 0])[:3]
    )
    estado = "SILENCIO" if state.silent else ("LOCK" if engine.clock.locked else "buscando")

    # La confianza de compas se muestra siempre, enganche o no. Si nunca
    # engancha hace falta saber si esta en 0.05 (no hay metrica que detectar)
    # o en 0.28 (rozando el umbral y solo hay que bajarlo un poco).
    indice = engine.clock.beat_index(now)
    if engine.bars.locked and indice is not None:
        # El '?' avisa de que el 1 y el 3 empatan: la rejilla es correcta pero
        # el compas puede estar desplazado medio compas.
        duda = "?" if engine.bars.ambiguous else " "
        compas = f"{engine.bars.beat_in_bar(indice) + 1}/{engine.bars.beats_per_bar}{duda}"
    else:
        compas = "-"

    sys.stdout.write(
        f"\r{mode:<10} BPM {bpm} conf {state.confidence:4.2f} {estado:<9} "
        f"compas {compas:<5} bconf {engine.bars.confidence:4.2f}  "
        f"g/m/a {niveles}  rgb {r:.2f},{g:.2f},{b:.2f}  "
        f"env {sent} err {failed} jit {limiter.jitter.mean_ms:.2f}ms   "
    )
    sys.stdout.flush()
