"""Identifica que luz fisica corresponde a cada canal Entertainment."""

from __future__ import annotations

import time

from ..config import Config, load_hue_credentials
from ..hue.backends import DEFAULT_BACKEND, StreamError
from ..hue.client import EntertainmentSession
from ..hue.rest import BridgeError
from ..timing import RateLimiter, TimerResolution

APAGADO = (0.0, 0.0, 0.0)
COLORES = ((1.0, 0.0, 0.0), (0.0, 0.3, 1.0), (0.0, 1.0, 0.2), (1.0, 1.0, 0.0))
NOMBRES = ("ROJO", "AZUL", "VERDE", "AMARILLO")


def _frame(canal: int, count: int) -> dict[int, tuple[float, float, float]]:
    """Enciende solo un canal para que el indice tenga una luz observable."""
    color = COLORES[canal % len(COLORES)]
    return {i: color if i == canal else APAGADO for i in range(count)}


def run_identify(
    cfg: Config,
    seconds: float,
    rounds: int,
    area_id: str | None = None,
    backend: str = DEFAULT_BACKEND,
) -> int:
    """Recorre los canales y deja al usuario anotar su posicion fisica.

    Se repite cada color durante varios frames porque el bridge cierra la
    sesion si deja de recibir paquetes; un unico paquete puede perderse en UDP
    y haria que un canal pareciera ausente.
    """
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
        print("completa el handshake. Comprueba que Hue Sync este cerrado.")
        return 1

    sent = failed = 0
    try:
        count = session.channel_count or 1
        limiter = RateLimiter(cfg.render.fps)
        print(f"Sesion abierta. {count} canal(es), {rounds} vuelta(s), "
              f"{seconds:.1f} s por canal.\n")
        with TimerResolution(1):
            for vuelta in range(rounds):
                print(f"VUELTA {vuelta + 1}/{rounds}")
                for canal in range(count):
                    print(f"  CANAL {canal} en {NOMBRES[canal % len(NOMBRES)]}")
                    fin = time.perf_counter() + seconds
                    frame = _frame(canal, count)
                    while time.perf_counter() < fin:
                        limiter.tick()
                        if session.send(frame):
                            sent += 1
                        else:
                            failed += 1
    except KeyboardInterrupt:
        print("\nInterrumpido")
    finally:
        session.stop()
        print("Sesion cerrada (action: stop enviado).")

    print(f"Paquetes: {sent} enviados, {failed} fallidos")
    if failed:
        print(f"AVISO: {failed} frames no salieron. Revisa la red o baja render.fps.")
    return 0
