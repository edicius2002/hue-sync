"""Orquestador del analisis: audio crudo -> AudioState publicado.

Dos piezas:

* `AnalysisEngine` es sincrono y puro. Se le pasan muestras y produce estado.
  Sirve igual para audio en vivo que para senal sintetica, que es lo que
  permite validar el algoritmo sin tocar el hardware.
* `LiveAnalyzer` es el hilo que lee del ring buffer y lo alimenta.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from .analysis.bands import BandLevels
from .analysis.beatclock import BeatClock
from .analysis.odf import SpectralAnalyzer
from .analysis.tempo import TempoTracker
from .config import AnalysisConfig
from .state import AudioState, StatePublisher


class ClockMapper:
    """Convierte tiempo-de-stream a tiempo de pared (perf_counter).

    Sigue el *minimo* offset observado con una deriva lenta hacia arriba, en
    vez de promediar. Promediar metería el jitter del scheduler del hilo de
    analisis directamente en el timing del beat; el seguimiento por minimo se
    queda con el mejor caso, que es el que refleja la latencia real.
    """

    def __init__(self, creep_per_second: float = 0.002) -> None:
        self.creep = creep_per_second
        self._offset: float | None = None
        self._last_wall = 0.0

    def observe(self, stream_t: float, wall_t: float) -> None:
        measured = wall_t - stream_t
        if self._offset is None:
            self._offset = measured
        else:
            allowed = self._offset + self.creep * max(0.0, wall_t - self._last_wall)
            self._offset = min(measured, allowed)
        self._last_wall = wall_t

    def to_wall(self, stream_t: float) -> float:
        return stream_t + (self._offset or 0.0)

    @property
    def offset(self) -> float:
        return self._offset or 0.0


class AnalysisEngine:
    def __init__(self, samplerate: int, cfg: AnalysisConfig) -> None:
        self.samplerate = samplerate
        self.cfg = cfg

        self.spectral = SpectralAnalyzer(
            samplerate,
            fft_size=cfg.fft_size,
            hop=cfg.hop,
            bands=cfg.band_edges,
            low_cutoff_hz=cfg.low_cutoff_hz,
        )
        self.tempo = TempoTracker(
            frame_rate=self.spectral.frame_rate,
            min_bpm=cfg.min_bpm,
            max_bpm=cfg.max_bpm,
            history_seconds=cfg.history_seconds,
            prior_bpm=cfg.prior_bpm,
            prior_width=cfg.prior_width,
            harmonics=cfg.harmonics,
            smoothing_seconds=cfg.smoothing_seconds,
            min_history_seconds=cfg.min_history_seconds,
            salience_scale=cfg.salience_scale,
        )
        self.clock = BeatClock(
            phase_gain=cfg.phase_gain,
            period_gain=cfg.period_gain,
            min_confidence=cfg.min_confidence,
            full_confidence=cfg.full_confidence,
        )
        self.bands = BandLevels(
            n_bands=len(cfg.band_edges),
            peak_decay=cfg.band_peak_decay,
            attack=cfg.band_attack,
            release=cfg.band_release,
        )
        self.mapper = ClockMapper()
        self.publisher = StatePublisher()

        self._last_estimate_t = 0.0
        self._frames_analyzed = 0
        self._silence_since: float | None = None

    def feed(self, samples: np.ndarray, start_sample: int, wall_t: float | None = None) -> None:
        if wall_t is None:
            wall_t = time.perf_counter()
        if len(samples) == 0:
            return

        rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
        silent = rms < self.cfg.silence_rms

        frames = self.spectral.process(samples, start_sample)
        if not frames:
            return

        self.mapper.observe(frames[-1].t, wall_t)
        dt = len(frames) / self.spectral.frame_rate

        # El tempo se sigue sobre todo con graves; el espectro completo entra
        # con poco peso, solo para no perder el pulso en pasajes sin bombo.
        w_low, w_full = self.cfg.tempo_low_weight, self.cfg.tempo_full_weight
        for f in frames:
            self.tempo.push(w_low * f.flux_low + w_full * f.flux, f.t)
        self._frames_analyzed += len(frames)

        band_levels = self.bands.update(frames[-1].bands, dt)

        stream_now = frames[-1].t
        if silent:
            if self._silence_since is None:
                self._silence_since = stream_now
            elif stream_now - self._silence_since > self.cfg.silence_timeout:
                self.clock.reset()
        else:
            self._silence_since = None

        if (
            not silent
            and stream_now - self._last_estimate_t >= self.cfg.estimate_interval
        ):
            self._last_estimate_t = stream_now
            est = self.tempo.estimate()
            if est is not None:
                # El BeatClock vive en tiempo de pared, que es donde tiene que
                # vivir el render y el envio DTLS.
                self.clock.update(
                    type(est)(
                        bpm=est.bpm,
                        period=est.period,
                        last_beat_time=self.mapper.to_wall(est.last_beat_time),
                        confidence=est.confidence,
                    ),
                    self.mapper.to_wall(stream_now),
                )

        self.publisher.publish(
            AudioState(
                t=stream_now,
                bpm=self.clock.bpm,
                confidence=self.clock.confidence,
                locked=self.clock.locked,
                flux=frames[-1].flux,
                bands=band_levels,
                rms=rms,
                silent=silent,
                frames_analyzed=self._frames_analyzed,
            )
        )

    @property
    def state(self) -> AudioState:
        return self.publisher.state


class LiveAnalyzer:
    """Hilo que drena el ring buffer hacia el AnalysisEngine."""

    def __init__(self, capture, engine: AnalysisEngine, poll_interval: float = 0.005) -> None:  # noqa: ANN001
        self.capture = capture
        self.engine = engine
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._read_index = 0

    def _run(self) -> None:
        buf = self.capture.buffer
        max_chunk = self.engine.samplerate  # como mucho 1 s por vuelta
        while not self._stop.is_set():
            samples, new_index = buf.read_since(self._read_index, max_chunk)
            self._read_index = new_index
            if len(samples):
                self.engine.feed(samples, new_index - len(samples))
            else:
                time.sleep(self.poll_interval)

    def start(self) -> None:
        self._read_index = self.capture.buffer.total_written
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="analysis", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
