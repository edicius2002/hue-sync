"""Chroma: reparto de energia entre las 12 clases de altura.

Sirve para que el color siga la **armonia** en vez del timbre. El mapeo por
bandas graves/medios/agudos responde a como suena la mezcla, asi que parpadea
con cada golpe de bateria; el chroma responde a que notas suenan, asi que se
mantiene quieto mientras no cambie el acorde y se mueve cuando cambia.

## Por que un FFT propio y mas grande

El analizador de la ODF usa 1024 muestras porque necesita resolucion temporal
para el ritmo. Eso da 46.9 Hz por bin a 48 kHz, y un semitono solo supera esa
anchura por encima de **788 Hz**: con ese FFT no se puede distinguir un Do de
un Do# en el registro donde viven las fundamentales.

Con 8192 muestras la resolucion baja a 5.9 Hz y los semitonos se resuelven
desde 99 Hz, que cubre el registro util. El precio es resolucion temporal, pero
aqui no importa: los acordes cambian cada uno o dos segundos, no cada 5 ms.

## Por que solo los picos

Sumar todos los bins funciona con acordes aislados pero se hunde en una mezcla
completa: la bateria reparte energia por las 12 clases y aplana la
distribucion. Medido sobre grabaciones reales, la tonalidad de la musica
quedaba en 0.03 contra 0.008 del ruido blanco, apenas 3.9x. Quedandose solo
con los maximos locales del espectro sube a 8.8x, porque el contenido tonal
produce parciales estrechos y la percusion no.

Tambien se probo el blanqueo espectral, que es la otra receta habitual, y
empeora mucho: baja la separacion a 1.3x.
"""

from __future__ import annotations

import numpy as np

N_PITCH_CLASSES = 12
A4_HZ = 440.0
A4_MIDI = 69


def _local_maxima(x: np.ndarray) -> np.ndarray:
    """Bins que superan a sus dos vecinos.

    Es lo que separa armonia de percusion en una mezcla completa. El contenido
    tonal produce parciales estrechos, o sea maximos afilados; la bateria
    produce energia de banda ancha sin relieve. Medido sobre grabaciones
    reales, quedarse solo con los picos sube la separacion entre musica y
    ruido de 3.9x a 8.8x sin perder estabilidad.
    """
    picos = np.zeros(len(x), dtype=bool)
    if len(x) > 2:
        picos[1:-1] = (x[1:-1] > x[:-2]) & (x[1:-1] > x[2:])
    return picos


def _entropy_tonality(chroma: np.ndarray) -> float:
    """Cuanto se aparta el reparto de ser uniforme.

    Se mide por entropia y NO por la magnitud de la media vectorial. La media
    vectorial parece la medida natural pero no funciona, y merece la pena
    entender por que: las notas de una triada mayor estan a 120 y 90 grados en
    el circulo cromatico, asi que sus vectores casi se cancelan. Medido, un Do
    mayor daba 0.14 y el ruido blanco 0.13, o sea que no separaba nada.

    La entropia si: una triada concentra la energia en 3 de 12 clases y deja el
    resto casi a cero, mientras que la percusion reparte por igual.
    """
    total = chroma.sum()
    if total <= 0:
        return 0.0
    p = chroma / total
    p = p[p > 0]
    entropia = float(-np.sum(p * np.log(p)))
    return float(np.clip(1.0 - entropia / float(np.log(N_PITCH_CLASSES)), 0.0, 1.0))


class ChromaAnalyzer:
    def __init__(
        self,
        samplerate: int,
        fft_size: int = 8192,
        hop: int = 2048,
        fmin: float = 100.0,
        fmax: float = 2000.0,
        smoothing: float = 0.93,
        tonality_smoothing: float = 0.97,
        peaks_only: bool = True,
        hue_glide: float = 0.0,
    ) -> None:
        """
        fmin/fmax acotan donde se mira. Por debajo de fmin el FFT no resuelve
        semitonos; por encima de fmax dominan los armonicos, y el tercer
        armonico cae una quinta arriba, o sea en OTRA clase de altura. Ampliar
        el rango hacia arriba no anade informacion, anade ruido tonal.
        """
        self.samplerate = samplerate
        self.fft_size = fft_size
        self.hop = hop
        self.smoothing = smoothing
        self.tonality_smoothing = tonality_smoothing
        self.peaks_only = peaks_only
        self.hue_glide = hue_glide
        self.frame_rate = samplerate / hop

        self._window = np.hanning(fft_size).astype(np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._chroma = np.zeros(N_PITCH_CLASSES, dtype=np.float64)
        self._tonality = 0.0
        self._seen = 0
        self._hue = 0.0

        freqs = np.fft.rfftfreq(fft_size, 1.0 / samplerate)
        usable = (freqs >= fmin) & (freqs <= fmax)
        self._bins = np.flatnonzero(usable)
        midi = A4_MIDI + 12.0 * np.log2(freqs[usable] / A4_HZ)
        self._classes = np.rint(midi).astype(int) % N_PITCH_CLASSES

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._chroma[:] = 0.0
        self._tonality = 0.0
        self._seen = 0

    @property
    def ready(self) -> bool:
        return self._seen > 0

    def process(self, samples: np.ndarray) -> np.ndarray | None:
        """Consume muestras. Devuelve el chroma suavizado si hubo frame nuevo."""
        self._pending = np.concatenate((self._pending, samples))
        actualizado = False

        offset = 0
        while len(self._pending) - offset >= self.fft_size:
            chunk = self._pending[offset : offset + self.fft_size]
            mag = np.abs(np.fft.rfft(chunk * self._window))
            pesos = mag[self._bins]
            if self.peaks_only:
                pesos = np.where(_local_maxima(pesos), pesos, 0.0)
            crudo = np.bincount(
                self._classes,
                weights=pesos,
                minlength=N_PITCH_CLASSES,
            )
            total = crudo.sum()
            if total > 0:
                crudo = crudo / total
                alpha = 1.0 if self._seen == 0 else (1.0 - self.smoothing)
                self._chroma += alpha * (crudo - self._chroma)
                bruta = _entropy_tonality(self._chroma)
                beta = 1.0 if self._seen == 0 else (1.0 - self.tonality_smoothing)
                self._tonality += beta * (bruta - self._tonality)
                self._update_hue()
                self._seen += 1
                actualizado = True
            offset += self.hop

        if offset:
            self._pending = self._pending[offset:]
        return self._chroma.copy() if actualizado else None

    @property
    def chroma(self) -> np.ndarray:
        return self._chroma.copy()

    def _update_hue(self) -> None:
        """Desliza el color hacia el centroide, por el camino corto del circulo.

        Viene a cero por defecto, y merece la pena explicar por que despues de
        haber intentado dos cosas que no funcionaron.

        Cuantizar a la clase dominante con histeresis, que es lo que arreglo el
        seguimiento de compas, aqui NO sirve: en una triada de Do las tres
        notas pesan casi igual (0.18 / 0.20 / 0.28), asi que el maximo es una
        moneda al aire incluso con material limpio. Sobre la progresion
        sintetica C-F-G-C, con 3 cambios reales, la clase dominante cambiaba 11
        veces, y ningun ajuste de histeresis acertaba los 3 sin callar tambien
        los cambios de verdad.

        Suavizar fuerte tampoco: cuesta precision sin comprar estabilidad. Con
        deslizamiento 0.96, volver al mismo acorde daba un color desviado 0.24
        en el circulo, contra 0.09 sin el, mientras el movimiento total apenas
        bajaba.

        Lo que de verdad arregla la inestabilidad es no fiarse de la armonia
        cuando no la hay, y eso vive en `harmony_min_tonality`. Con el umbral
        bien puesto, el movimiento del color en mezcla densa cae de 0.016 por
        frame a 0.0004. El parametro se conserva por si algun material se
        beneficia, pero no hace falta.
        """
        objetivo = self.raw_hue
        if self._seen == 0:
            self._hue = objetivo
            return
        # Diferencia circular: ir por el camino corto del circulo de color.
        delta = (objetivo - self._hue + 0.5) % 1.0 - 0.5
        self._hue = (self._hue + (1.0 - self.hue_glide) * delta) % 1.0

    @property
    def hue(self) -> float:
        """Angulo 0..1 en el circulo cromatico, ya estabilizado."""
        return self._hue

    @property
    def raw_hue(self) -> float:
        """Centroide continuo sin estabilizar. Solo para diagnostico."""
        total = self._chroma.sum()
        if total <= 0:
            return 0.0
        angulos = 2.0 * np.pi * np.arange(N_PITCH_CLASSES) / N_PITCH_CLASSES
        vector = np.sum(self._chroma * np.exp(1j * angulos))
        return (float(np.angle(vector)) / (2.0 * np.pi)) % 1.0

    @property
    def tonality(self) -> float:
        """Cuanto contenido tonal hay: 0 = ruido o percusion, 1 = una nota sola.

        Se suaviza mas fuerte que el propio chroma, y eso no es un detalle. La
        tonalidad gobierna la mezcla entre color armonico y color espectral, y
        en musica real oscila dentro de la banda de transicion, asi que sin
        suavizar hace que el color vaya y venga entre dos fuentes muy
        distintas. Medido, ese vaiven dejaba el modo harmony MENOS estable que
        el espectral (0.031 contra 0.019); con el suavizado pasa a 0.016.
        """
        return self._tonality

    @property
    def centroid(self) -> tuple[float, float]:
        return self.hue, self.tonality

    @property
    def dominant(self) -> int:
        """Clase con mas energia ahora mismo, sin estabilizar."""
        return int(np.argmax(self._chroma))
