"""Reloj de beat de rodadura libre, enganchado por PLL.

Esta es la pieza que diferencia el proyecto del Hue Sync oficial. En vez de
reaccionar a beats detectados ("hubo un beat -> flash"), se mantiene un
oscilador de fase que corre solo y se corrige suavemente contra las
estimaciones del TempoTracker.

Consecuencias practicas:

* Se puede consultar `time_to_next_beat()` en cualquier instante, o sea que un
  efecto puede animar *hacia* el beat en vez de despues de el.
* Se puede compensar la latencia total del pipeline (captura + analisis + DTLS
  + Zigbee) preguntando por el estado en `now + compensacion`, o sea emitir el
  comando *antes* del beat. Un sistema reactivo no puede hacer esto.
* El analisis corre a ~172 fps y el render a 50 Hz sin estorbarse.
"""

from __future__ import annotations

import math

from .tempo import TempoEstimate


class BeatClock:
    def __init__(
        self,
        phase_gain: float = 0.45,
        period_gain: float = 0.12,
        min_confidence: float = 0.15,
        full_confidence: float = 0.6,
        octave_snap_count: int = 3,
        stale_after: float = 3.0,
    ) -> None:
        self.phase_gain = phase_gain
        self.period_gain = period_gain
        self.min_confidence = min_confidence
        self.full_confidence = full_confidence
        self.octave_snap_count = octave_snap_count
        self.stale_after = stale_after

        self.period: float | None = None
        self.confidence = 0.0
        self._anchor = 0.0
        self._last_update = 0.0
        self._octave_votes = 0
        self._pending_period = 0.0
        self._last_poll: float | None = None

    @property
    def locked(self) -> bool:
        return self.period is not None

    @property
    def bpm(self) -> float | None:
        return 60.0 / self.period if self.period else None

    def is_stale(self, now: float) -> bool:
        return not self.locked or (now - self._last_update) > self.stale_after

    def reset(self) -> None:
        self.period = None
        self.confidence = 0.0
        self._octave_votes = 0
        self._last_poll = None

    def update(self, est: TempoEstimate, now: float) -> None:
        if est.confidence < self.min_confidence:
            return

        self._last_update = now
        self.confidence = est.confidence

        if self.period is None:
            self.period = est.period
            self._anchor = est.last_beat_time
            return

        # Salto de octava: no se acepta a la primera, hace falta que varias
        # estimaciones consecutivas coincidan. Si no, un pasaje con doble de
        # densidad ritmica desengancharia el reloj.
        ratio = math.log2(est.period / self.period)
        if abs(ratio) > 0.25:
            if self._pending_period and abs(math.log2(est.period / self._pending_period)) < 0.1:
                self._octave_votes += 1
            else:
                self._octave_votes = 1
            self._pending_period = est.period
            if self._octave_votes >= self.octave_snap_count:
                self.period = est.period
                self._anchor = est.last_beat_time
                self._octave_votes = 0
            return

        self._octave_votes = 0

        # La confianza responde dos preguntas distintas y no deben compartir
        # escala: si aceptar la estimacion (min_confidence) y cuanto corregir.
        # Escalar la ganancia por la confianza cruda hace que el reloj deje de
        # corregir justo cuando la senal se pone dificil, que es al reves de lo
        # que conviene. Con full_confidence la ganancia esta al maximo en
        # cuanto la evidencia es razonable, y solo se reduce si es de verdad
        # marginal.
        trust = min(1.0, est.confidence / self.full_confidence)
        self.period += self.period_gain * trust * (est.period - self.period)

        # Error de fase respecto al beat predicho mas cercano, envuelto a
        # [-P/2, P/2] para no arrastrar el reloj un beat entero.
        k = round((est.last_beat_time - self._anchor) / self.period)
        predicted = self._anchor + k * self.period
        error = est.last_beat_time - predicted
        self._anchor += self.phase_gain * trust * error

    def time_to_next_beat(self, now: float) -> float | None:
        """Segundos hasta el proximo beat. Siempre > 0."""
        if self.period is None:
            return None
        k = math.floor((now - self._anchor) / self.period) + 1
        return (self._anchor + k * self.period) - now

    def phase(self, now: float) -> float:
        """Posicion dentro del beat: 0.0 justo en el beat, ->1.0 antes del siguiente."""
        if self.period is None:
            return 0.0
        return ((now - self._anchor) / self.period) % 1.0

    def poll_beats(self, now: float) -> int:
        """Cuantos beats cruzaron desde la llamada anterior.

        Para el hilo de render, que corre mas lento que el analisis.
        """
        if self.period is None:
            self._last_poll = now
            return 0
        if self._last_poll is None:
            self._last_poll = now
            return 0
        before = math.floor((self._last_poll - self._anchor) / self.period)
        after = math.floor((now - self._anchor) / self.period)
        self._last_poll = now
        return max(0, after - before)
