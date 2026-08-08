"""Estado compartido entre el hilo de analisis y el de render.

Se publica por intercambio atomico de un objeto inmutable: el lector nunca ve
un estado a medio escribir y no hay lock en el camino critico del render.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class AudioState:
    t: float = 0.0
    """Tiempo del ultimo frame analizado, en el reloj del stream."""
    bpm: float | None = None
    confidence: float = 0.0
    locked: bool = False
    flux: float = 0.0
    bands: np.ndarray = field(default_factory=lambda: np.zeros(3))
    """Graves, medios, agudos normalizados a 0..1."""
    rms: float = 0.0
    silent: bool = True
    frames_analyzed: int = 0
    dropped_samples: int = 0


class StatePublisher:
    """Publicacion sin lock por rebind de referencia (atomico en CPython)."""

    def __init__(self) -> None:
        self._state = AudioState()

    def publish(self, state: AudioState) -> None:
        self._state = state

    @property
    def state(self) -> AudioState:
        return self._state
