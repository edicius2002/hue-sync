"""STFT -> flujo espectral (onset detection function) + energia por bandas.

Se calcula una sola FFT por frame y de ahi salen las dos cosas, porque el
analisis corre a ~172 fps y no conviene duplicar trabajo.

El flujo espectral con compresion logaritmica es el ODF clasico: comprime el
rango dinamico para que un hi-hat suave pese parecido a un bombo fuerte, lo
que hace la deteccion mucho menos dependiente del volumen maestro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Compresion logaritmica del espectro: log(1 + GAMMA * |X|).
# Valores altos aplanan mas; 1000 es el valor habitual en la literatura.
GAMMA = 1000.0

DEFAULT_BANDS = ((20.0, 250.0), (250.0, 2000.0), (2000.0, 16000.0))


@dataclass(frozen=True)
class Frame:
    """Un frame de analisis."""

    index: int
    t: float
    """Tiempo (s) del centro de la ventana, derivado del contador de muestras."""
    flux: float
    """Flujo sobre todo el espectro. Bueno para onsets, malo para tempo."""
    flux_low: float
    """Flujo restringido a graves.

    Solo ve bombo y caja, no hi-hats. Es la diferencia entre detectar el pulso
    real y detectar las corcheas: una balada a 76 BPM con hats en corcheas
    genera periodicidad a 152 en el espectro completo, pero a 76 en graves.
    """
    bands: np.ndarray
    """Energia RMS cruda por banda (graves, medios, agudos)."""
    sub_bass: float = 0.0
    """Energia RMS cruda de 20-80 Hz, separada de la banda de graves.

    El nivel publicado se normaliza por tema a proposito: el techo debe seguir
    la dinamica del 808 de ESE tema, no comparar su masterizacion con otra.
    Por eso sus valores no son comparables entre canciones. Dentro de un tema
    si aporta informacion distinta de `bands[0]`: sobre el estado publicado,
    muestreado a 50 fps despues de 3 s de arranque, la correlacion es 0.364 en
    travis y 0.420 en summer. Un 808 de trap se mueve casi independiente de
    los graves; en hard techno el bombo es los graves y la redundancia es
    esperada.
    """


class SpectralAnalyzer:
    def __init__(
        self,
        samplerate: int,
        fft_size: int = 1024,
        hop: int = 256,
        bands: tuple[tuple[float, float], ...] = DEFAULT_BANDS,
        low_cutoff_hz: float = 500.0,
    ) -> None:
        self.samplerate = samplerate
        self.fft_size = fft_size
        self.hop = hop
        self.frame_rate = samplerate / hop

        self._window = np.hanning(fft_size).astype(np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._pending_start = 0  # indice de muestra global de _pending[0]
        self._prev_spec: np.ndarray | None = None
        self._frame_index = 0

        freqs = np.fft.rfftfreq(fft_size, 1.0 / samplerate)
        self._band_masks = [
            (freqs >= lo) & (freqs < hi) for lo, hi in bands
        ]
        self._sub_bass_mask = (freqs >= 20.0) & (freqs < 80.0)
        self._n_low = max(2, int(np.searchsorted(freqs, low_cutoff_hz)))

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._prev_spec = None
        self._frame_index = 0

    def process(self, samples: np.ndarray, start_sample: int) -> list[Frame]:
        """Consume muestras y devuelve los frames completos que salieron.

        `start_sample` es el indice global de la primera muestra de `samples`,
        y es lo que da timestamps estables aunque el hilo lector se atrase.
        """
        if len(self._pending) == 0:
            self._pending_start = start_sample
        self._pending = np.concatenate((self._pending, samples))

        frames: list[Frame] = []
        offset = 0
        while len(self._pending) - offset >= self.fft_size:
            chunk = self._pending[offset : offset + self.fft_size]
            spec = np.abs(np.fft.rfft(chunk * self._window))
            log_spec = np.log1p(GAMMA * spec)

            if self._prev_spec is None:
                flux = flux_low = 0.0
            else:
                diff = log_spec - self._prev_spec
                pos = np.maximum(diff, 0.0)
                flux = float(pos.sum() / len(pos))
                flux_low = float(pos[: self._n_low].sum() / self._n_low)
            self._prev_spec = log_spec

            band_energy = np.array(
                [float(np.sqrt(np.mean(spec[m] ** 2))) if m.any() else 0.0
                 for m in self._band_masks],
                dtype=np.float32,
            )
            sub_bass = (
                float(np.sqrt(np.mean(spec[self._sub_bass_mask] ** 2)))
                if self._sub_bass_mask.any()
                else 0.0
            )

            center = self._pending_start + offset + self.fft_size / 2.0
            frames.append(
                Frame(
                    index=self._frame_index,
                    t=center / self.samplerate,
                    flux=flux,
                    flux_low=flux_low,
                    bands=band_energy,
                    sub_bass=sub_bass,
                )
            )
            self._frame_index += 1
            offset += self.hop

        if offset:
            self._pending = self._pending[offset:]
            self._pending_start += offset
        return frames
