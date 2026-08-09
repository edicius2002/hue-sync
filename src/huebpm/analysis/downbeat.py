"""Deteccion del "1" del compas a partir de la energia de cada beat.

El BeatClock sabe *cuando* cae cada beat pero no cual de ellos es el primero
del compas. Sin eso, cambiar de color "en el beat" cae en un tiempo cualquiera
y se ve arbitrario aunque este perfectamente sincronizado.

La idea es simple y barata: casi toda la musica en 4/4 pone mas peso en graves
en el 1 (y algo en el 3). Acumulando la energia de graves de cada beat en un
histograma modulo 4, el maximo senala el downbeat. Se acumula con decaimiento
para que un cambio de seccion pueda reubicar el compas sin arrastrar la
historia entera.
"""

from __future__ import annotations

import numpy as np


class BarTracker:
    def __init__(
        self,
        beats_per_bar: int = 4,
        beats_per_phrase: int = 16,
        decay: float = 0.92,
        min_confidence: float = 0.30,
    ) -> None:
        self.beats_per_bar = beats_per_bar
        self.beats_per_phrase = beats_per_phrase
        self.decay = decay
        self.min_confidence = min_confidence
        self._scores = np.zeros(beats_per_bar, dtype=np.float64)
        self._beats_seen = 0

    def reset(self) -> None:
        """Se llama cuando el reloj cambia de tempo o de fase: el histograma
        anterior ya no corresponde a los mismos beats."""
        self._scores[:] = 0.0
        self._beats_seen = 0

    def push_beat(self, beat_index: int, energy: float) -> None:
        self._scores *= self.decay
        self._scores[beat_index % self.beats_per_bar] += energy
        self._beats_seen += 1

    @property
    def offset(self) -> int:
        """Indice de beat (modulo compas) que hace de "1"."""
        return int(np.argmax(self._scores))

    @property
    def confidence(self) -> float:
        """0 = los cuatro tiempos pesan igual, 1 = uno domina por completo.

        Se mide contra el reparto uniforme, no contra cero: con cuatro
        posiciones, que el maximo se lleve un 25% no dice absolutamente nada.
        """
        total = self._scores.sum()
        if total <= 0 or self._beats_seen < self.beats_per_bar:
            return 0.0
        uniforme = 1.0 / self.beats_per_bar
        proporcion = float(self._scores.max() / total)
        return float(np.clip((proporcion - uniforme) / (1.0 - uniforme), 0.0, 1.0))

    @property
    def locked(self) -> bool:
        """Ojo con la ambiguedad de medio compas: si el bombo cae en el 1 y en
        el 3 con la misma fuerza, no hay forma de distinguirlos y el detector
        puede quedarse en el 3. Para luces eso desplaza el cambio de color
        medio compas, que se nota pero no arruina la sincronia."""
        return self.confidence >= self.min_confidence

    def beat_in_bar(self, beat_index: int) -> int:
        """Posicion del beat dentro del compas: 0 es el downbeat."""
        return (beat_index - self.offset) % self.beats_per_bar

    def beat_in_phrase(self, beat_index: int) -> int:
        return (beat_index - self.offset) % self.beats_per_phrase

    def bar_phase(self, beat_index: int, beat_phase: float) -> float:
        """Posicion continua dentro del compas, 0..1."""
        return (self.beat_in_bar(beat_index) + beat_phase) / self.beats_per_bar

    def phrase_phase(self, beat_index: int, beat_phase: float) -> float:
        """Posicion continua dentro de la frase, 0..1."""
        return (self.beat_in_phrase(beat_index) + beat_phase) / self.beats_per_phrase

    @property
    def scores(self) -> np.ndarray:
        """Histograma crudo. Publico para diagnostico, como `score_curve`."""
        return self._scores.copy()
