"""Prueba end-to-end del canal Entertainment, sin analisis de audio.

Separa dos preguntas que si se mezclan no hay quien depure: "el canal a las
luces funciona y con que latencia" y "el detector de beats acierta". Esto
responde solo la primera.
"""

from __future__ import annotations

import colorsys
import time

from ..config import Config, load_hue_credentials
from ..hue.backends import DEFAULT_BACKEND, StreamError
from ..hue.client import EntertainmentSession
from ..hue.rest import BridgeError
from ..timing import RateLimiter, TimerResolution


def run_huetest(
    cfg: Config, seconds: float, area_id: str | None = None, backend: str = DEFAULT_BACKEND
) -> int:
    try:
        creds = load_hue_credentials()
    except (FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    area = area_id or creds.entertainment_area_id
    if not area:
        print("No hay entertainment_area_id en hue_config.json ni se paso --area.")
        print("Mira 'run.py areas' y anade la clave, o usa --area <id>.")
        return 1

    print(f"Bridge {creds.bridge_ip}, area {area}, backend {backend}")
    session = EntertainmentSession(
        creds.bridge_ip, creds.username, creds.clientkey, area, backend=backend
    )

    try:
        session.start()
    except BridgeError as exc:
        print(f"\n{exc}")
        return 1
    except StreamError as exc:
        print(f"\n{exc}\n")
        print("El bridge acepta la REST y pone el area en 'active', pero no")
        print("completa el handshake. Comprueba:")
        print("  1. Cierra Hue Sync: compite por la misma entertainment area.")
        print("  2. Desenchufa el bridge 10 s.")
        return 1

    n = session.channel_count or 1
    print(f"Sesion abierta. {n} canal(es). Streaming a {cfg.render.fps:.0f} Hz "
          f"durante {seconds:.0f} s.\n")
    print("  Fase 1: barrido de color continuo  (comprueba fluidez)")
    print("  Fase 2: flashes a 1 Hz             (comprueba latencia a ojo)\n")

    limiter = RateLimiter(cfg.render.fps)
    sent = failed = 0
    start = time.perf_counter()

    try:
        with TimerResolution(1):
            while True:
                now = limiter.tick()
                elapsed = now - start
                if elapsed > seconds:
                    break

                if elapsed < seconds / 2:
                    hue = (elapsed / 4.0) % 1.0
                    rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                else:
                    on = (elapsed % 1.0) < 0.12
                    rgb = (1.0, 1.0, 1.0) if on else (0.0, 0.0, 0.05)

                if session.send({i: rgb for i in range(n)}):
                    sent += 1
                else:
                    failed += 1

                if int(elapsed) != int(elapsed - 1.0 / cfg.render.fps):
                    print(f"\r  {elapsed:4.1f}s  enviados {sent}  fallidos {failed}  "
                          f"jitter {limiter.jitter.mean_ms:.2f} ms", end="", flush=True)
    except KeyboardInterrupt:
        print("\n  interrumpido")
    finally:
        # Se para el cronometro ANTES de cerrar: stop() hace una llamada REST
        # que tarda casi un segundo y falsearia la tasa hacia abajo.
        elapsed_total = time.perf_counter() - start
        print()
        session.stop()
        print("Sesion cerrada (action: stop enviado).")

    rate = sent / max(1e-9, elapsed_total)
    print(f"\nPaquetes: {sent} enviados, {failed} fallidos  ->  {rate:.1f} Hz efectivos")
    print(f"Jitter del loop: media {limiter.jitter.mean_ms:.2f} ms, "
          f"max {limiter.jitter.max_ms:.2f} ms")
    if failed:
        print(f"AVISO: {failed} frames no salieron. Revisa la red o baja render.fps.")
    return 0
