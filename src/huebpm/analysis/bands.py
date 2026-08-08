"""Normalizacion adaptativa de las bandas graves/medios/agudos.

La energia RMS cruda no sirve para mapear a color: depende del volumen maestro
y del mastering del tema. Lo que se quiere es "que tan fuerte estan los graves
*ahora* comparado con lo que ha venido sonando", que es lo que da un seguidor
de pico con caida lenta.
"""

from __future__ import annotations

import numpy as np


class BandLevels:
    def __init__(
        self,
        n_bands: int = 3,
        peak_decay: float = 0.5,
        attack: float = 0.005,
        release: float = 0.15,
        noise_floor: float = 1e-5,
    ) -> None:
        """
        peak_decay: factor por segundo con que cae el seguidor de pico.
        attack/release: constantes de tiempo (s) del suavizado asimetrico.
        """
        self.peak_decay = peak_decay
        self.attack = attack
        self.release = release
        self.noise_floor = noise_floor

        self._peak = np.full(n_bands, noise_floor, dtype=np.float64)
        self._level = np.zeros(n_bands, dtype=np.float64)

    def update(self, raw: np.ndarray, dt: float) -> np.ndarray:
        raw = np.asarray(raw, dtype=np.float64)

        decay = self.peak_decay ** dt
        self._peak = np.maximum(raw, self._peak * decay)
        np.maximum(self._peak, self.noise_floor, out=self._peak)

        target = np.clip(raw / self._peak, 0.0, 1.0)

        rising = target > self._level
        tau = np.where(rising, self.attack, self.release)
        alpha = 1.0 - np.exp(-dt / np.maximum(tau, 1e-6))
        self._level += alpha * (target - self._level)

        return self._level.copy()

    @property
    def level(self) -> np.ndarray:
        return self._level.copy()
