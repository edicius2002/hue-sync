"""Estimacion de tempo y fase por autocorrelacion de la ODF.

Corre cada ~0.5 s sobre una ventana de ~6 s. El tempo no necesita ir rapido:
lo que tiene que ir rapido es la *fase*, y de eso se encarga el BeatClock, que
extrapola entre estimaciones.

Sobre errores de octava (detectar 160 cuando son 80): se combaten con dos
cosas, un prior log-gaussiano centrado en ~120 BPM y refuerzo armonico de la
autocorrelacion. Ninguna de las dos es infalible, pero juntas cubren la mayoria
de la musica con pulso estable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ScoreCurve:
    """Estado interno de una estimacion, para diagnostico y tuning."""

    odf: np.ndarray
    lags: np.ndarray
    bpms: np.ndarray
    acf: np.ndarray
    raw: np.ndarray
    """Autocorrelacion cruda en cada lag candidato."""
    harmonic: np.ndarray
    """Tras sumar los armonicos."""
    prior: np.ndarray
    final: np.ndarray

    def salience(self, scale: float = 10.0) -> float:
        """Confianza 0..1: cuanto sobresale el pico sobre el fondo de la curva.

        Usar la autocorrelacion cruda como confianza (que es lo que se hacia
        antes) no funciona, porque su escala depende del material: un click
        track sintetico da 0.8 y una pista producida da 0.3 aunque el pulso
        este igual de claro. El sidechain, la reverb y los sintes sostenidos
        llenan la ODF y bajan la correlacion absoluta sin que el tempo sea mas
        ambiguo.

        Lo que si es comparable entre materiales es cuantas desviaciones
        robustas sobresale el pico respecto al resto de candidatos. Se usa MAD
        en vez de desviacion tipica porque la propia curva tiene picos en los
        armonicos, y esos inflarian una desviacion clasica.
        """
        raw = self.raw
        median = float(np.median(raw))
        mad = float(np.median(np.abs(raw - median)))
        spread = 1.4826 * mad
        if spread < 1e-9:
            return 0.0
        z = (float(raw.max()) - median) / spread
        return float(np.clip(z / scale, 0.0, 1.0))


@dataclass(frozen=True)
class TempoEstimate:
    bpm: float
    period: float
    """Periodo del beat en segundos."""
    last_beat_time: float
    """Tiempo absoluto (s) del beat mas reciente dentro de la ventana."""
    confidence: float
    """0..1. Por debajo de ~0.25 el resultado no es fiable."""


def _moving_average(x: np.ndarray, width: int) -> np.ndarray:
    """Media movil centrada, via suma acumulada (O(n))."""
    if width < 2:
        return np.zeros_like(x)
    pad = width // 2
    padded = np.pad(x, (pad, width - pad - 1), mode="edge")
    cumsum = np.cumsum(np.insert(padded, 0, 0.0))
    return (cumsum[width:] - cumsum[:-width]) / width


class TempoTracker:
    def __init__(
        self,
        frame_rate: float,
        min_bpm: float = 60.0,
        max_bpm: float = 180.0,
        history_seconds: float = 6.0,
        prior_bpm: float = 120.0,
        prior_width: float = 0.9,
        smoothing_seconds: float = 1.5,
        harmonics: tuple[tuple[int, float], ...] = ((2, 0.5), (4, 0.25)),
        min_history_seconds: float = 3.0,
        salience_scale: float = 10.0,
    ) -> None:
        self.frame_rate = frame_rate
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.prior_bpm = prior_bpm
        self.prior_width = prior_width
        self.harmonics = harmonics
        self.salience_scale = salience_scale

        self.size = int(history_seconds * frame_rate)
        self._hist = np.zeros(self.size, dtype=np.float32)
        self._pos = 0
        self._filled = 0
        self._last_t = 0.0
        self._smooth_width = max(2, int(smoothing_seconds * frame_rate))
        self._min_frames = min(self.size, int(min_history_seconds * frame_rate))

        self._lag_min = max(2, int(round(60.0 / max_bpm * frame_rate)))

    @property
    def ready(self) -> bool:
        return self._filled >= self._min_frames

    def _history(self) -> np.ndarray:
        """ODF acumulada, en orden cronologico.

        Se trabaja con lo que haya: esperar a llenar los 6 s completos impone
        un suelo duro de 6 s antes de la primera estimacion. Con 3 s ya se
        puede enganchar de forma provisional, y la ventana crece sola.
        """
        if self._filled < self.size:
            return self._hist[: self._filled]
        return np.concatenate((self._hist[self._pos :], self._hist[: self._pos]))

    def push(self, flux: float, t: float) -> None:
        # Buffer circular: el reordenado se hace solo en estimate(), que corre
        # a 2 Hz, no a los ~172 fps de push().
        self._hist[self._pos] = flux
        self._pos = (self._pos + 1) % self.size
        self._last_t = t
        if self._filled < self.size:
            self._filled += 1

    def _normalized(self) -> np.ndarray:
        """ODF con media movil restada y rectificada. Esto es lo que hace que
        funcione igual con la musica bajita que con la fuerte.

        La ventana tiene que abarcar *varios* beats. Si se acerca a un solo
        periodo de beat, restar la media movil actua como un notch justo en la
        frecuencia del pulso y borra lo que se quiere medir: a 174 BPM el beat
        cae cada 65 frames, asi que una ventana de 65 frames hace desaparecer
        el tempo real y el detector se va a un submultiplo.
        """
        x = self._history().astype(np.float64)
        x = x - _moving_average(x, min(self._smooth_width, max(2, len(x) // 2)))
        np.maximum(x, 0.0, out=x)
        peak = x.max()
        if peak > 0:
            x /= peak
        return x

    def score_curve(self) -> ScoreCurve | None:
        """Curva de puntuacion por lag. Publica a proposito: es la unica forma
        de entender por que el detector eligio un tempo y no otro."""
        if not self.ready:
            return None

        x = self._normalized()
        if x.sum() < 1e-6:
            return None  # silencio

        # El lag maximo depende de cuanta historia haya, no del tamano nominal
        # del buffer: con 3 s acumulados no se pueden medir periodos de 1 s.
        lag_max = min(len(x) // 2, int(round(60.0 / self.min_bpm * self.frame_rate)))
        if lag_max <= self._lag_min:
            return None

        # Autocorrelacion via FFT con normalizacion *sesgada* (dividir por n, no
        # por el solape de cada lag). El estimador insesgado infla los lags
        # largos, donde quedan pocas muestras solapadas, y eso hacia que el
        # refuerzo armonico premiara tempos falsos: un candidato lento gana
        # porque sus armonicos caen en la zona ruidosa de la correlacion.
        n = len(x)
        size = 1 << int(np.ceil(np.log2(2 * n)))
        spec = np.fft.rfft(x - x.mean(), size)
        acf = np.fft.irfft(spec * np.conj(spec), size)[:n]
        if acf[0] <= 0:
            return None
        acf = acf / acf[0]

        lags = np.arange(self._lag_min, lag_max + 1)

        # Refuerzo armonico: un lag verdadero tambien correlaciona en 2x y 4x,
        # lo que empuja la eleccion hacia el pulso real y no hacia su doble.
        # Se ignoran armonicos mas alla de n/2: ahi la estimacion ya no es
        # fiable ni con normalizacion sesgada.
        # El periodo real casi nunca cae en un lag entero. Si se muestrea el
        # armonico exactamente en k*lag se falla el pico por redondeo, y el
        # error crece con k: para un beat de 64.66 frames, el candidato entero
        # 65 busca en 130/195/260 mientras los picos estan en 129.3/194/258.6.
        # Un candidato falso a 1.5x, que da un lag casi exacto, acierta sus
        # armonicos y gana injustamente. Por eso se toma el maximo en un
        # entorno proporcional al multiplo.
        limit = n // 2
        harmonic_score = acf[lags].copy()
        for mult, weight in self.harmonics:
            harmonic = lags * mult
            window = max(1, mult // 2)
            valid = (harmonic + window) < limit
            best = np.full(len(lags), -np.inf)
            for offset in range(-window, window + 1):
                best = np.maximum(best, acf[np.clip(harmonic + offset, 0, limit - 1)])
            harmonic_score[valid] += weight * best[valid]

        bpms = 60.0 * self.frame_rate / lags
        prior = np.exp(
            -0.5 * (np.log2(bpms / self.prior_bpm) / self.prior_width) ** 2
        )
        return ScoreCurve(
            odf=x,
            lags=lags,
            bpms=bpms,
            acf=acf,
            raw=acf[lags],
            harmonic=harmonic_score,
            prior=prior,
            final=harmonic_score * prior,
        )

    def estimate(self) -> TempoEstimate | None:
        curve = self.score_curve()
        if curve is None:
            return None
        x, lags, score = curve.odf, curve.lags, curve.final
        n = len(x)

        best = int(np.argmax(score))
        if float(score[best]) <= 0:
            return None

        period_frames = float(lags[best])
        # Refinamiento subframe por parabola sobre los vecinos del pico.
        if 0 < best < len(score) - 1:
            y0, y1, y2 = score[best - 1], score[best], score[best + 1]
            denom = y0 - 2 * y1 + y2
            if denom != 0:
                period_frames += 0.5 * (y0 - y2) / denom

        confidence = curve.salience(self.salience_scale)

        offset = self._estimate_phase(x, period_frames)
        # Beat mas reciente, en frames desde el final de la ventana.
        frames_back = (n - 1 - offset) % period_frames
        last_beat_time = self._last_t - frames_back / self.frame_rate

        return TempoEstimate(
            bpm=60.0 * self.frame_rate / period_frames,
            period=period_frames / self.frame_rate,
            last_beat_time=last_beat_time,
            confidence=confidence,
        )

    def _estimate_phase(self, x: np.ndarray, period_frames: float) -> float:
        """Offset (en frames) del tren de pulsos que mejor casa con la ODF.

        Se pondera exponencialmente hacia el presente: si el tempo derivo un
        poco a lo largo de la ventana, gana la fase reciente, que es la unica
        que sirve para predecir el siguiente beat.
        """
        n = len(x)
        tau = n / 3.0
        weights = np.exp(-(n - 1 - np.arange(n)) / tau)
        weighted = x * weights

        best_offset, best_score = 0.0, -1.0
        for offset in range(int(round(period_frames))):
            idx = np.arange(offset, n, period_frames)
            score = float(weighted[np.round(idx).astype(int).clip(0, n - 1)].sum())
            if score > best_score:
                best_score, best_offset = score, float(offset)
        return best_offset
