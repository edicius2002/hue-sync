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
        decay: float = 0.97,
        min_confidence: float = 0.10,
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
        """Cuanta estructura metrica hay: 0 = los tiempos pesan igual, 1 = uno
        se lo lleva todo.

        Es la distancia de variacion total al reparto uniforme, y NO "cuanto
        domina el maximo". La diferencia importa: medido sobre Billie Jean, el
        bombo cae en el 1 y en el 3, y esos dos tiempos se llevan el 70% de la
        energia frente al 30% de los otros dos. La estructura es inequivoca,
        pero mirando solo el maximo (35%) la metrica daba 0.14 y no enganchaba
        nunca. Con la desviacion completa da 0.27 y separa bien: el mismo
        calculo sobre house four-on-the-floor, donde de verdad no hay metrica,
        da 0.05.
        """
        total = self._scores.sum()
        if total <= 0 or self._beats_seen < self.beats_per_bar:
            return 0.0
        reparto = self._scores / total
        uniforme = 1.0 / self.beats_per_bar
        desviacion = float(np.abs(reparto - uniforme).sum())
        return float(np.clip(desviacion / (2.0 * (1.0 - uniforme)), 0.0, 1.0))

    @property
    def ambiguous(self) -> bool:
        """True si el segundo tiempo mas fuerte casi empata con el primero.

        Pasa siempre que el bombo va en 1 y 3 con la misma fuerza, que es el
        patron mas comun del pop y el rock. Sabemos donde esta la rejilla del
        compas pero no cual de los dos es el "1": el efecto puede acabar
        cambiando de color en el 3. Se desplaza medio compas y se nota, pero
        sigue siendo rítmico y consistente, que es lo que importa para luces.
        """
        if self._scores.sum() <= 0:
            return True
        ordenados = np.sort(self._scores)[::-1]
        return bool(ordenados[1] > 0.85 * ordenados[0])

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
