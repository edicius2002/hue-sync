"""Validacion offline del detector contra ground truth sintetico.

Mide lo unico que decide la viabilidad del proyecto: cuantos milisegundos se
equivoca el reloj al *predecir* el siguiente beat. Un error por debajo de
~25 ms es imperceptible con luces; por encima de ~60 ms se nota.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Config
from ..engine import AnalysisEngine
from ..testing.synth import click_track

SAMPLERATE = 48000


@dataclass
class CaseResult:
    label: str
    true_bpm: float
    detected_bpm: float | None
    lock_time: float | None
    mean_error_ms: float
    p90_error_ms: float
    max_error_ms: float
    samples: int

    @property
    def ratio(self) -> float | None:
        if not self.detected_bpm:
            return None
        return self.detected_bpm / self.true_bpm

    @property
    def octave_ok(self) -> bool:
        """El tempo detectado es el real o una octava suya (x2, /2...).

        Para luces esto importa menos de lo que parece: enganchar a 152 en un
        tema de 76 sigue viendose sincronizado, porque un flash de cada dos cae
        en el pulso. Lo que arruina el efecto es una relacion no entera, tipo
        detectar 116 en un tema de 174: ahi la luz deriva contra la musica.
        """
        r = self.ratio
        if r is None:
            return False
        return abs(round(np.log2(r)) - np.log2(r)) < 0.04

    @property
    def exact(self) -> bool:
        return self.detected_bpm is not None and abs(self.detected_bpm - self.true_bpm) < 1.5

    @property
    def ok(self) -> bool:
        return self.octave_ok and self.samples > 0 and self.mean_error_ms < 25.0


def run_case(
    label: str,
    bpm: float,
    cfg: Config,
    duration: float = 30.0,
    jitter_ms: float = 0.0,
    noise_level: float = 0.0,
    warmup: float = 10.0,
    seed: int = 0,
) -> CaseResult:
    audio, beat_times = click_track(
        bpm, duration, SAMPLERATE, jitter_ms=jitter_ms, noise_level=noise_level, seed=seed
    )
    engine = AnalysisEngine(SAMPLERATE, cfg.analysis)

    block = cfg.audio.blocksize
    errors: list[float] = []
    lock_time: float | None = None
    next_probe = warmup

    for start in range(0, len(audio) - block, block):
        chunk = audio[start : start + block]
        block_end = (start + block) / SAMPLERATE
        # wall_t == tiempo de stream: el ClockMapper queda con offset conocido
        # y se puede comparar todo en la misma escala.
        engine.feed(chunk, start, wall_t=block_end)

        if lock_time is None and engine.clock.locked:
            lock_time = block_end

        if block_end >= next_probe and engine.clock.locked:
            next_probe = block_end + 0.1
            wall_now = engine.mapper.to_wall(block_end)
            ttnb = engine.clock.time_to_next_beat(wall_now)
            period_det = engine.clock.period
            if ttnb is not None and period_det:
                predicted = (wall_now + ttnb) - engine.mapper.offset
                # Solo el interior: cerca de los bordes el "beat mas cercano"
                # no esta definido y el error medido seria un artefacto.
                if not (beat_times[1] < predicted < beat_times[-2]):
                    continue
                nearest = beat_times[np.argmin(np.abs(beat_times - predicted))]
                # Error envuelto al periodo *detectado*: si el reloj engancho a
                # la octava, los pulsos siguen cayendo en una rejilla musical
                # coherente y eso no debe contarse como error de fase.
                raw = predicted - nearest
                wrapped = (raw + period_det / 2) % period_det - period_det / 2
                errors.append(wrapped * 1000.0)

    err = np.abs(np.array(errors)) if errors else np.array([])
    return CaseResult(
        label=label,
        true_bpm=bpm,
        detected_bpm=engine.clock.bpm,
        lock_time=lock_time,
        mean_error_ms=float(err.mean()) if err.size else float("nan"),
        p90_error_ms=float(np.percentile(err, 90)) if err.size else float("nan"),
        max_error_ms=float(err.max()) if err.size else float("nan"),
        samples=int(err.size),
    )


DEFAULT_CASES = [
    ("house 128", 128.0, 0.0, 0.0),
    ("hip-hop 90", 90.0, 0.0, 0.0),
    ("dnb 174", 174.0, 0.0, 0.0),
    ("balada 76", 76.0, 0.0, 0.0),
    ("128 + jitter 8ms", 128.0, 8.0, 0.0),
    ("128 + ruido", 128.0, 0.0, 0.02),
    ("100 + jitter + ruido", 100.0, 6.0, 0.015),
]


def run_selftest(cfg: Config, duration: float = 30.0) -> int:
    print(f"\nSelf-test del detector de BPM  ({SAMPLERATE} Hz, {duration:.0f}s por caso)")
    print(
        f"hop={cfg.analysis.hop}  fft={cfg.analysis.fft_size}  "
        f"resolucion ODF={1000 * cfg.analysis.hop / SAMPLERATE:.1f} ms\n"
    )
    header = (f"{'caso':<22} {'real':>7} {'detect':>8} {'x':>5} {'lock':>7} "
              f"{'err med':>9} {'p90':>8} {'max':>8}   estado")
    print(header)
    print("-" * len(header))

    results = []
    for label, bpm, jitter, noise in DEFAULT_CASES:
        r = run_case(label, bpm, cfg, duration=duration, jitter_ms=jitter, noise_level=noise)
        results.append(r)
        detected = f"{r.detected_bpm:.1f}" if r.detected_bpm else "--"
        ratio = f"{r.ratio:.2f}" if r.ratio else "--"
        lock = f"{r.lock_time:.1f}s" if r.lock_time else "--"
        if not r.ok:
            estado = "FALLA"
        elif r.exact:
            estado = "OK"
        else:
            estado = "OK (octava)"
        print(
            f"{r.label:<22} {r.true_bpm:>7.1f} {detected:>8} {ratio:>5} {lock:>7} "
            f"{r.mean_error_ms:>8.1f}ms {r.p90_error_ms:>7.1f}ms {r.max_error_ms:>7.1f}ms   {estado}"
        )

    passed = sum(1 for r in results if r.ok)
    exact = sum(1 for r in results if r.exact)
    print(f"\n{passed}/{len(results)} con rejilla coherente y error medio < 25 ms")
    print(f"{exact}/{len(results)} ademas con el BPM exacto (+-1.5)\n")
    return 0 if passed == len(results) else 1
