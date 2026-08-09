"""Deteccion de onsets: los golpes sueltos que no caen en el pulso.

La ODF ya los ve —redobles, stabs, palmas fuera de tiempo— pero hasta ahora
solo se usaba para estimar el tempo, o sea que todo lo que no fuera periodico
se descartaba. Aqui se leen los picos directamente.

El metodo es peak-picking con umbral adaptativo: un frame es onset si supera a
sus vecinos y ademas destaca sobre la media local. El umbral tiene que ser
adaptativo y no fijo porque la ODF no esta normalizada en amplitud absoluta, y
un valor que es un golpe enorme en un pasaje tranquilo es ruido de fondo en un
estribillo.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Onset:
    t: float
    """Tiempo del golpe, en la escala de la ODF."""
    strength: float
    """Cuanto sobresalio del fondo local, normalizado a 0..1."""


class OnsetDetector:
    def __init__(
        self,
        frame_rate: float,
        window: float = 0.15,
        delta: float = 1.6,
        lookahead: int = 3,
        min_separation: float = 0.05,
    ) -> None:
        """
        window: segundos de contexto para la media local.
        delta: cuantas desviaciones por encima de esa media hace falta.
        lookahead: frames que se esperan para confirmar que es un maximo. Es
            latencia pura, pero a 187 fps son unos 16 ms y el render ya va con
            compensacion de latencia por delante.
        min_separation: dos golpes mas juntos que esto cuentan como uno. Sin
            esto, un solo transitorio dispara varias veces en frames seguidos.
        """
        self.frame_rate = frame_rate
        self.delta = delta
        self.lookahead = max(1, lookahead)
        self.min_separation = min_separation

        self._window_frames = max(4, int(window * frame_rate))
        self._hist: deque[tuple[float, float]] = deque(
            maxlen=self._window_frames + self.lookahead + 1
        )
        self._last_onset_t = -1e9
        self._peak = 1e-9

    def reset(self) -> None:
        self._hist.clear()
        self._last_onset_t = -1e9
        self._peak = 1e-9

    def push(self, value: float, t: float) -> Onset | None:
        """Consume un frame de ODF. Devuelve el onset confirmado, si lo hay.

        El onset que devuelve es de hace `lookahead` frames: no se puede saber
        que un valor es un maximo local hasta haber visto lo que viene despues.
        """
        self._hist.append((t, value))
        if len(self._hist) < self._window_frames + self.lookahead + 1:
            return None

        datos = list(self._hist)
        idx = len(datos) - 1 - self.lookahead
        cand_t, cand_v = datos[idx]

        # Maximo local: nadie a su alrededor le gana.
        vecinos = datos[max(0, idx - self.lookahead) : idx] + datos[idx + 1 :]
        if any(v >= cand_v for _, v in vecinos):
            return None

        contexto = [v for _, v in datos[:idx]]
        if not contexto:
            return None
        media = sum(contexto) / len(contexto)
        varianza = sum((v - media) ** 2 for v in contexto) / len(contexto)
        desviacion = varianza**0.5

        if cand_v < media + self.delta * desviacion:
            return None
        if cand_t - self._last_onset_t < self.min_separation:
            return None

        self._last_onset_t = cand_t
        # Normalizacion por pico historico con decaimiento: da una fuerza
        # comparable entre pasajes sin depender del volumen maestro.
        self._peak = max(cand_v, self._peak * 0.999)
        return Onset(t=cand_t, strength=min(1.0, cand_v / self._peak))
