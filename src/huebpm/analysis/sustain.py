"""Medicion continua de cuan estable es la envolvente del audio."""

from __future__ import annotations

from collections import deque

import numpy as np

from .odf import Frame
from .onsets import OnsetDetector


def _between(value: float, low: float, high: float) -> float:
    """Escala ``value`` a 0..1 entre dos limites, sin salirse del rango."""
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


class SustainDetector:
    """Convierte la forma temporal reciente en un nivel de sostenimiento.

    El coeficiente de variacion de la energia RMS total mide directamente la
    envolvente: un pad o ruido de amplitud estable queda alto, mientras que
    los ataques elevan la dispersion. La tasa de onsets solo aporta una
    correccion pequena para secuencias de golpes claramente separadas.
    """

    def __init__(
        self,
        frame_rate: float,
        window: float = 2.5,
        transition: float = 0.75,
        energy_full: float = 0.255,
        energy_zero: float = 0.310,
        onsets_full: float = 0.0,
        onsets_zero: float = 8.0,
        onset_crest: float = 10.0,
    ) -> None:
        """Configura la ventana y los limites en unidades fisicas.

        ``window`` de 2.5 s conserva cuatro valores entre 0.35 y 0.65 al
        barrer bateria sobre un pad entre ganancias 0.60 y 0.75. ``transition``
        esta en segundos y no en beats para que un cambio de tempo no altere
        la suavidad visual.
        """
        if frame_rate <= 0:
            raise ValueError("frame_rate debe ser positivo")
        if window <= 0:
            raise ValueError("window debe ser positivo")
        if transition <= 0:
            raise ValueError("transition debe ser positivo")
        if energy_full < 0:
            raise ValueError("energy_full debe estar en 0..1")
        if energy_zero <= energy_full:
            raise ValueError("energy_zero debe ser mayor que energy_full")
        if onsets_full < 0:
            raise ValueError("onsets_full debe ser no negativo")
        if onsets_zero <= onsets_full:
            raise ValueError("onsets_zero debe ser mayor que onsets_full")
        if onset_crest <= 1.0:
            raise ValueError("onset_crest debe ser mayor que uno")
        self.frame_rate = frame_rate
        self.window = window
        self.transition = transition
        self.energy_full = energy_full
        self.energy_zero = energy_zero
        self.onsets_full = onsets_full
        self.onsets_zero = onsets_zero
        self.onset_crest = onset_crest
        self._window_frames = max(2, int(round(window * frame_rate)))
        self._frames: deque[Frame] = deque(maxlen=self._window_frames)
        # La ODF de una nota fija conserva un pequeno serrucho de fase. Un
        # umbral mas estricto evita contarlo como decenas de ataques blandos.
        self._onsets = OnsetDetector(frame_rate, delta=3.5, min_separation=0.1)
        self._onset_times: deque[float] = deque()
        self._sustain = 0.0
        self._last_t: float | None = None

    def reset(self) -> None:
        """Olvida la ventana para no mezclar dos streams de audio."""
        self._frames.clear()
        self._onsets.reset()
        self._onset_times.clear()
        self._sustain = 0.0
        self._last_t = None

    def push(self, frame: Frame) -> float:
        """Consume un frame y devuelve sostenimiento continuo en 0..1."""
        onset = self._onsets.push(frame.flux, frame.t)
        self._frames.append(frame)
        if onset is not None:
            candidate = next(f.flux for f in reversed(self._frames) if f.t == onset.t)
            average = float(np.mean([f.flux for f in self._frames]))
            # El flujo de una nota fija tiene pequenos picos por fuga entre
            # bins. Solo cuentan como ataques los que dominan ese fondo.
            if candidate >= self.onset_crest * max(average, 1e-8):
                self._onset_times.append(onset.t)
        cutoff = frame.t - self.window
        while self._onset_times and self._onset_times[0] < cutoff:
            self._onset_times.popleft()

        if len(self._frames) < self._window_frames:
            self._last_t = frame.t
            return self._sustain

        target = self._measure()
        if self._last_t is not None:
            dt = max(0.0, frame.t - self._last_t)
            # Filtro de primer orden: la rampa permanece igual al cambiar BPM.
            alpha = 1.0 - np.exp(-dt / self.transition)
            self._sustain += (target - self._sustain) * alpha
        self._last_t = frame.t
        return float(np.clip(self._sustain, 0.0, 1.0))

    def _measure(self) -> float:
        onset_rate = len(self._onset_times) / self.window
        onset_score = 1.0 - _between(onset_rate, self.onsets_full, self.onsets_zero)

        bands = np.stack([f.bands for f in self._frames]).astype(np.float64)
        energy = np.sum(bands, axis=1)
        mean_energy = float(np.mean(energy))
        variation = float(np.std(energy) / mean_energy) if mean_energy > 1e-8 else 1.0
        energy_score = 1.0 - _between(variation, self.energy_full, self.energy_zero)

        # La energia domina: la tasa evita que golpes muy separados parezcan
        # estables, sin anular un pad con negras a 120 BPM.
        return float(0.95 * energy_score + 0.05 * onset_score)
