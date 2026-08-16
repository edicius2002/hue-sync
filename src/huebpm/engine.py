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
from .analysis.chroma import ChromaAnalyzer
from .analysis.downbeat import BarTracker
from .analysis.odf import SpectralAnalyzer
from .analysis.onsets import OnsetDetector
from .analysis.sustain import SustainDetector
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
        self.bars = BarTracker(
            beats_per_bar=cfg.beats_per_bar,
            beats_per_phrase=cfg.beats_per_phrase,
            decay=cfg.downbeat_decay,
            min_confidence=cfg.downbeat_min_confidence,
            unlock_confidence=cfg.downbeat_unlock_confidence,
            offset_hold=cfg.downbeat_offset_hold,
        )
        self.onsets = OnsetDetector(
            frame_rate=self.spectral.frame_rate,
            window=cfg.onset_window,
            delta=cfg.onset_delta,
            lookahead=cfg.onset_lookahead,
            min_separation=cfg.onset_min_separation,
        )
        self.sustain = SustainDetector(
            self.spectral.frame_rate,
            window=cfg.sustain_window,
            transition=cfg.sustain_transition,
            energy_full=cfg.sustain_energy_full,
            energy_zero=cfg.sustain_energy_zero,
        )
        self.chroma = ChromaAnalyzer(
            samplerate,
            fft_size=cfg.chroma_fft_size,
            hop=cfg.chroma_hop,
            fmin=cfg.chroma_fmin,
            fmax=cfg.chroma_fmax,
            smoothing=cfg.chroma_smoothing,
            tonality_smoothing=cfg.chroma_tonality_smoothing,
            peaks_only=cfg.chroma_peaks_only,
            hue_glide=cfg.chroma_hue_glide,
        )
        self.mapper = ClockMapper()
        self.publisher = StatePublisher()

        self._last_estimate_t = 0.0
        self._frames_analyzed = 0
        self._last_onset_time = -1e9
        self._last_onset_strength = 0.0
        self._current_beat: int | None = None
        self._beat_energy = 0.0
        self._clock_generation = self.clock.generation
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
        sustain = 0.0
        for f in frames:
            self.tempo.push(w_low * f.flux_low + w_full * f.flux, f.t)
            sustain = self.sustain.push(f)
        self._frames_analyzed += len(frames)

        self._detect_onsets(frames)
        self.chroma.process(samples)
        band_levels = self.bands.update(frames[-1].bands, dt)
        self._accumulate_beat_energy(frames)

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
                chroma_hue=self.chroma.hue,
                tonality=self.chroma.tonality,
                sustain=sustain,
                last_onset_time=self._last_onset_time,
                last_onset_strength=self._last_onset_strength,
                rms=rms,
                silent=silent,
                frames_analyzed=self._frames_analyzed,
            )
        )

    def _detect_onsets(self, frames) -> None:  # noqa: ANN001
        """Guarda solo los golpes que NO caen en el pulso.

        Los que caen en el beat ya los cubre la envolvente del reloj;
        acentuarlos otra vez solo duplica el mismo destello. Lo que aporta esto
        son los redobles, stabs y palmas a contratiempo, que hasta ahora se
        descartaban porque el analisis solo buscaba periodicidad.
        """
        margen = self.cfg.onset_offbeat_margin
        for f in frames:
            onset = self.onsets.push(f.flux, f.t)
            if onset is None:
                continue
            wall = self.mapper.to_wall(onset.t)
            if self.clock.locked:
                fase = self.clock.phase(wall)
                distancia = min(fase, 1.0 - fase)
                if distancia < margen:
                    continue
            self._last_onset_time = wall
            self._last_onset_strength = onset.strength

    def _accumulate_beat_energy(self, frames) -> None:  # noqa: ANN001
        """Mide la fuerza del golpe de graves de cada beat para el BarTracker.

        Dos decisiones que no son obvias:

        **Energia cruda, no flujo espectral.** La ODF esta log-comprimida a
        proposito (`log1p(1000*|X|)`), que es lo que la hace invariante al
        volumen y permite seguir el tempo con la musica bajita. Esa misma
        compresion aplasta la diferencia entre un bombo normal y uno acentuado
        justo cuando se quiere medirla. Para el compas hace falta la magnitud
        real de la banda de graves.

        **Pico, no suma.** El acento del downbeat es un transitorio. Sumar
        sobre todo el beat lo diluye entre el bajo sostenido, que reparte por
        igual en los cuatro tiempos y no distingue nada.
        """
        if self.clock.generation != self._clock_generation:
            # El reloj se reengancho o salto de octava: los indices de beat ya
            # no significan lo mismo y el histograma acumulado es basura.
            self.bars.reset()
            self._clock_generation = self.clock.generation
            self._current_beat = None
            self._beat_energy = 0.0

        if not self.clock.locked:
            return

        for f in frames:
            index = self.clock.beat_index(self.mapper.to_wall(f.t))
            if index is None:
                continue
            if self._current_beat is None:
                self._current_beat = index
            elif index != self._current_beat:
                self.bars.push_beat(self._current_beat, self._beat_energy)
                self._current_beat = index
                self._beat_energy = 0.0
            self._beat_energy = max(self._beat_energy, float(f.bands[0]))

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
