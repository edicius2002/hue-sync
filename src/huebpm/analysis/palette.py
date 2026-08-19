"""Que color de una paleta corta le toca al espectro, sin parpadear.

`spectrum_color` mezcla graves/medios/agudos de forma continua, y esa mezcla
tiende al gris: tres colores sumados por peso dan marron mucho mas a menudo de
lo que dan rojo. Para que la luz solo muestre colores fuertes hay que ELEGIR
uno, no promediarlos, y eso convierte una mezcla en una decision.

Una decision necesita memoria, y los efectos de este proyecto son funciones
puras de datos ya resueltos. Por eso el escalon se calcula aqui, en el
analisis, y se publica en `AudioState` como un entero: el look solo indexa una
paleta.

Medido sobre los ocho WAV de referencia a 50 fps, tras el warmup:

* El centroide ponderado por bandas NO recorre 0..1. El p10-p90 global es
  0.398..0.576, o sea que todo lo util cabe en 0.18. Umbrales repartidos sobre
  0..1 dejarian la luz clavada en el color central para siempre; los de
  `spectrum_step_edges` son los terciles medidos.
* Cuantizar sin mas da 12.1 cambios de color por segundo. Eso es un estrobo,
  no "colores fuertes". La histeresis sola tampoco basta: baja a 8.1.
* Lo que de verdad lo arregla es suavizar y exigir permanencia. Con tau=0.15,
  margen=0.002 y 0.5 s de permanencia el ritmo baja a poco mas de un color por
  segundo, medido tema a tema en el propio codigo cableado.
* Cuantos MENOS escalones haya, mas tiempo pasan encendidos los extremos. Con
  cinco colores el primero y el ultimo se repartian el 21% del tiempo entre
  los dos, y el 79% se lo comian los del medio. Con tres suben al 58%. Por eso
  un color debil duele mas en el centro que en un extremo.

El margen es pequeno a proposito. Los umbrales exteriores caen cerca de las
colas de la distribucion, asi que un margen grande no estabiliza: mata los
colores de los extremos. Medido, a 0.004 ya hay temas que dejan de ver un
color entero (0.0% del tiempo); 0.002 es el mayor que los conserva los ocho.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def band_centroid(bands: Sequence[float]) -> float | None:
    """Donde cae el peso del espectro: 0 = todo graves, 1 = todo agudos.

    Se calcula sobre las bandas ya normalizadas y no sobre un centroide FFT
    crudo porque `BandLevels` mide cada banda contra su propio pico reciente.
    Eso es lo que hace que la senal se mueva: un centroide absoluto se queda
    casi fijo en musica producida, que es justo el fallo que se quiere evitar.
    """
    valores = list(bands) + [0.0, 0.0, 0.0]
    bass, mid, treble = valores[0], valores[1], valores[2]
    total = bass + mid + treble
    if total < 1e-6:
        return None
    return (0.5 * mid + 1.0 * treble) / total


class SpectrumStep:
    """Escalon de paleta con suavizado, histeresis y permanencia minima."""

    def __init__(
        self,
        edges: Sequence[float],
        tau: float = 0.15,
        margin: float = 0.002,
        dwell: float = 0.5,
    ) -> None:
        self.edges = tuple(float(x) for x in edges)
        self.tau = float(tau)
        self.margin = float(margin)
        self.dwell = float(dwell)
        self._smooth: float | None = None
        self._step = 0
        self._held = 0.0

    @property
    def step(self) -> int:
        return self._step

    def update(self, bands: Sequence[float], dt: float) -> int:
        """Avanza `dt` segundos y devuelve el escalon vigente.

        En silencio no se decide nada: se conserva el ultimo escalon. Elegir
        uno con el centroide indefinido haria que la luz saltase de color al
        entrar y salir de un silencio, que es movimiento sin causa musical.
        """
        self._held += max(0.0, dt)
        centro = band_centroid(bands)
        if centro is None:
            return self._step

        if self._smooth is None:
            # El primer centroide se adopta entero. La permanencia protege un
            # color ya elegido; al arrancar no hay ninguno, y esperar medio
            # segundo solo dejaria la luz en el primer color de la paleta sin
            # que nada lo haya decidido.
            self._smooth = centro
            self._step = self._cuantizar(centro)
            self._held = 0.0
            return self._step

        alpha = 1.0 - math.exp(-max(0.0, dt) / max(self.tau, 1e-9))
        self._smooth += alpha * (centro - self._smooth)

        if self._held < self.dwell:
            return self._step

        destino = self._cuantizar(self._smooth)
        if destino == self._step:
            return self._step

        # El margen se mide contra el borde que hay que cruzar, no contra el
        # del destino: lo que se resiste es salir del escalon actual.
        if destino > self._step:
            cruza = self._smooth > self.edges[self._step] + self.margin
        else:
            cruza = self._smooth < self.edges[self._step - 1] - self.margin

        if cruza:
            self._step = destino
            self._held = 0.0
        return self._step

    def _cuantizar(self, valor: float) -> int:
        escalon = 0
        for borde in self.edges:
            if valor <= borde:
                break
            escalon += 1
        return escalon
