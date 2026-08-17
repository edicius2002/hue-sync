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
    chroma_hue: float = 0.0
    """Posicion en el circulo cromatico, 0..1. Sigue la armonia, no el timbre."""
    tonality: float = 0.0
    """0 = percusion o ruido, 1 = una nota sola. Es lo que evita colorear un
    redoble con un tono arbitrario."""
    sustain: float = 0.0
    """Cuanto se sostiene el sonido: 0 = transitorio o percusivo, 1 = sostenido.

    Mide SOLO la envolvente temporal: cresta de la ODF, tasa de onsets,
    variacion de energia por banda. NO dice nada de si lo sostenido es
    armonico, y eso es deliberado: una cama de ruido o unos aplausos puntuan
    alto aqui. Excluirlos es cosa del efecto, cruzando este valor con
    `tonality` a traves de la puerta de EffectsConfig.

    Publicarlo crudo y sin filtrar sigue la misma regla que `last_onset_time`:
    el analisis mide y el efecto decide. Si el detector aplicara la puerta
    necesitaria la tonalidad, que vive en otro modulo y corre a otra frecuencia
    de frame (23.4 fps el chroma contra 187.5 la ODF).
    """
    last_onset_time: float = -1e9
    """Instante del ultimo golpe fuera de tiempo, en tiempo de pared.

    Se publica el instante y no un nivel ya calculado para que los efectos
    sigan siendo funciones puras: la caida se deriva de `now - last_onset_time`.
    """
    last_onset_strength: float = 0.0

    sub_bass: float = 0.0
    """Nivel 20-80 Hz normalizado, separado de `bands[0]`.

    `bands[0]` cubre 20-250 Hz y mezcla el bombo con el bajo y con los medios
    graves. En trap y hip-hop el 808 vive por debajo de 80 Hz y es la voz que
    llena la habitacion, asi que separarlo es lo que permite mandarlo a la luz
    cenital sin arrastrar el resto de la mezcla.

    Arranca en 0.0 y nadie lo puebla todavia.
    """
    beat_strength: float = 0.0
    """Cuanto pego el ultimo beat, 0..1. NO es la confianza del tempo.

    `confidence` mide si hay periodicidad; esto mide si ESTE golpe fue fuerte.
    Un tema puede tener confianza 1.0 y golpes de intensidad muy distinta, y
    hoy `beat_envelope` tiene forma fija: marca CUANDO cae el beat, no CUANTO
    pego. Sin esto no se puede acentuar solo lo que lo merece.

    Arranca en 0.0 y nadie lo puebla todavia.
    """
    onset_rate: float = 0.0
    """Onsets por segundo sobre una ventana corta.

    Distingue una base densa de golpes aislados, y discrimina de verdad:
    medido sobre 25 s, reggaeton da 3.09/s y house 1.59/s, casi el doble.
    `last_onset_strength` dice cuanto pego el ultimo; esto dice cuantos hay.

    Arranca en 0.0 y nadie lo puebla todavia.
    """

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
