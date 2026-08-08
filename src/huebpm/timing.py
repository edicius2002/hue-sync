"""Temporizacion de alta resolucion en Windows.

Detalle que hunde a la mayoria de proyectos parecidos: por defecto el timer
del sistema en Windows tiene una granularidad de ~15.6 ms. Un loop a 50 Hz
necesita ticks de 20 ms, o sea que `time.sleep()` a secas produce un patron
irregular de 15.6/31.2 ms y las luces se sienten temblorosas por mucho que el
detector de beats sea perfecto.

La solucion es pedir resolucion de 1 ms a winmm y hacer spin en el ultimo
tramo. Con eso el jitter baja de ~8 ms a menos de 1 ms.
"""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass

_SPIN_MARGIN = 0.0015  # ultimos 1.5 ms a base de spin


class TimerResolution:
    """Sube la resolucion del timer del sistema mientras dure el bloque."""

    def __init__(self, period_ms: int = 1) -> None:
        self.period_ms = period_ms
        self._active = False

    def __enter__(self) -> TimerResolution:
        if sys.platform == "win32":
            if ctypes.windll.winmm.timeBeginPeriod(self.period_ms) == 0:
                self._active = True
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        if self._active:
            ctypes.windll.winmm.timeEndPeriod(self.period_ms)
            self._active = False


def sleep_until(target: float) -> None:
    """Espera hasta `target` (escala de perf_counter) con precision sub-ms."""
    while True:
        remaining = target - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > _SPIN_MARGIN:
            time.sleep(remaining - _SPIN_MARGIN)
        else:
            # Spin: ceder el hilo mantiene el proceso amable con el scheduler
            # sin perder precision.
            while time.perf_counter() < target:
                pass
            return


@dataclass
class JitterStats:
    count: int = 0
    mean_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, error_s: float) -> None:
        err_ms = abs(error_s) * 1000.0
        self.count += 1
        self.mean_ms += (err_ms - self.mean_ms) / self.count
        self.max_ms = max(self.max_ms, err_ms)


class RateLimiter:
    """Loop de tasa fija sin deriva acumulada."""

    def __init__(self, fps: float) -> None:
        self.interval = 1.0 / fps
        self._next: float | None = None
        self.jitter = JitterStats()

    def tick(self) -> float:
        now = time.perf_counter()
        if self._next is None:
            self._next = now + self.interval
            return now
        sleep_until(self._next)
        now = time.perf_counter()
        self.jitter.add(now - self._next)
        self._next += self.interval
        # Si nos atrasamos mas de un intervalo entero, resincronizar en vez de
        # intentar recuperar el tiempo perdido a toda velocidad.
        if now > self._next:
            self._next = now + self.interval
        return now
