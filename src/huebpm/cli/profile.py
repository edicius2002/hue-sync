"""Tabla cruzada de varios WAV: una fila por tema, para calibrar umbrales.

`analyze` vuelca el detalle de UN fichero, segundo a segundo. Las decisiones
de calibracion (donde poner la puerta de tonalidad, si `bars` aporta, si
`sustain` se enciende) necesitan la vista de N temas a la vez. Esta tabla es
esa vista: BPM y evidencia, compas, tonalidad, sostenimiento, onsets y las
mezclas efectivas que de verdad activan un modo.

Los primeros segundos se descartan: chroma (FFT 8192) y sustain (ventana
2.5 s) arrancan en cero y contaminarian las medianas. El muestreo es a los
50 fps del render, no a la cadencia de los bloques de audio: son ritmos
distintos y mezclarlos sesga los porcentajes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Config
from ..effects.base import harmony_mix, sustain_mix
from ..engine import AnalysisEngine
from .analyze import load_wav
from .sync import _context

WARMUP_SECONDS = 3.0
"""Segundos iniciales que no entran en las estadisticas.

Las ventanas largas del analisis (chroma, sustain) se llenan desde cero.
Incluirlas baja las medianas de un tema sostenido y sube las de uno
percusivo, justo al reves de lo que se quiere leer.
"""


@dataclass(frozen=True)
class ProfileRow:
    """Una fila de la tabla: un tema, numeros comparables con los demas."""

    name: str
    bpm: float | None
    clock_lock_pct: float
    tempo_score: float | None
    """Score del candidato ganador al final. La confianza del reloj sola
    engana: un tema puede marcar 100% de enganche con un pico debil."""
    bar_lock_pct: float
    bar_conf: float
    tonal_p50: float
    tonal_max: float
    sustain_p50: float
    onsets_per_s: float
    harmony_mix_pct: float
    sustain_mix_pct: float


def _recortar(audio: np.ndarray, rate: int, start: float, duration: float | None) -> np.ndarray:
    begin = int(start * rate)
    if begin >= len(audio):
        return audio[:0]
    end = begin + int(duration * rate) if duration is not None else len(audio)
    return audio[begin:end]


def _tempo_score(engine: AnalysisEngine) -> float | None:
    curve = engine.tempo.score_curve()
    if curve is None or len(curve.final) == 0:
        return None
    return float(curve.final.max())


def profile_file(
    cfg: Config,
    path: Path,
    start: float = 0.0,
    duration: float | None = None,
    warmup: float = WARMUP_SECONDS,
) -> ProfileRow:
    """Analiza un WAV y resume el render a 50 fps, descartando el arranque.

    Motor nuevo en cada llamada: reusar el `AnalysisEngine` arrastra el
    histograma de compas y la historia de tempo al tema siguiente, y las
    filas dejan de ser independientes.
    """
    audio, rate = load_wav(path)
    audio = _recortar(audio, rate, start, duration)
    if len(audio) == 0:
        raise ValueError(
            f"{path.name}: no queda audio tras --start {start:.1f}"
            + (f" --duration {duration:.1f}" if duration is not None else "")
        )

    engine = AnalysisEngine(rate, cfg.analysis)
    block = cfg.audio.blocksize
    fps = cfg.render.fps
    dt = 1.0 / fps
    lookahead = cfg.render.latency_compensation_ms / 1000.0

    clock_lock = 0
    bar_lock = 0
    tonal = []
    sust = []
    hmix = []
    smix = []
    onsets: set[float] = set()
    n_frames = 0
    next_render = 0.0

    def tomar(t_real: float) -> None:
        nonlocal clock_lock, bar_lock, n_frames
        if t_real < warmup:
            return
        state = engine.state
        ctx = _context(engine, state, t_real + lookahead, 1, cfg, now_real=t_real)
        n_frames += 1
        if ctx.clock.locked:
            clock_lock += 1
        if ctx.bar_locked:
            bar_lock += 1
        tonal.append(float(state.tonality))
        sust.append(float(state.sustain))
        hmix.append(float(harmony_mix(ctx)))
        smix.append(float(sustain_mix(ctx)))
        golpe = float(state.last_onset_time)
        if warmup <= golpe <= t_real:
            onsets.add(golpe)

    for offset in range(0, len(audio) - block, block):
        t = (offset + block) / rate
        engine.feed(audio[offset : offset + block], offset, wall_t=t)
        while next_render <= t:
            tomar(next_render)
            next_render += dt

    ventana = max(1e-9, (len(audio) / rate) - warmup)
    if n_frames == 0:
        return ProfileRow(
            name=path.name,
            bpm=float(engine.clock.bpm) if engine.clock.bpm is not None else None,
            clock_lock_pct=0.0,
            tempo_score=_tempo_score(engine),
            bar_lock_pct=0.0,
            bar_conf=float(engine.bars.confidence),
            tonal_p50=0.0,
            tonal_max=0.0,
            sustain_p50=0.0,
            onsets_per_s=0.0,
            harmony_mix_pct=0.0,
            sustain_mix_pct=0.0,
        )

    return ProfileRow(
        name=path.name,
        bpm=float(engine.clock.bpm) if engine.clock.bpm is not None else None,
        clock_lock_pct=100.0 * clock_lock / n_frames,
        tempo_score=_tempo_score(engine),
        bar_lock_pct=100.0 * bar_lock / n_frames,
        bar_conf=float(engine.bars.confidence),
        tonal_p50=float(np.median(tonal)),
        tonal_max=float(np.max(tonal)),
        sustain_p50=float(np.median(sust)),
        onsets_per_s=len(onsets) / ventana,
        harmony_mix_pct=100.0 * float(np.mean(np.asarray(hmix) > 0.0)),
        sustain_mix_pct=100.0 * float(np.mean(np.asarray(smix) > 0.0)),
    )


def format_table(rows: list[ProfileRow]) -> str:
    """Tabla de ancho fijo: una ojeada, no un volcado."""
    header = (
        f"{'tema':<14} {'bpm':>6} {'lock':>5} {'score':>6} "
        f"{'compas':>6} {'bconf':>6} {'ton p50':>8} {'ton max':>8} "
        f"{'sus p50':>8} {'on/s':>5} {'hmix':>6} {'smix':>6}"
    )
    lineas = [header]
    for r in rows:
        bpm = f"{r.bpm:6.1f}" if r.bpm is not None else "    --"
        score = f"{r.tempo_score:6.3f}" if r.tempo_score is not None else "    --"
        lineas.append(
            f"{r.name:<14} {bpm} {r.clock_lock_pct:4.0f}% {score} "
            f"{r.bar_lock_pct:5.0f}% {r.bar_conf:6.3f} {r.tonal_p50:8.3f} "
            f"{r.tonal_max:8.3f} {r.sustain_p50:8.3f} {r.onsets_per_s:5.2f} "
            f"{r.harmony_mix_pct:5.1f}% {r.sustain_mix_pct:5.1f}%"
        )
    return "\n".join(lineas)


def run_profile(
    cfg: Config,
    paths: list[Path],
    start: float = 0.0,
    duration: float | None = None,
) -> int:
    """Imprime la tabla. Devuelve 1 si falta un fichero, sin traceback."""
    faltan = [p for p in paths if not p.exists()]
    if faltan:
        print(f"No existe {faltan[0]}", file=sys.stderr)
        return 1

    filas: list[ProfileRow] = []
    for path in paths:
        try:
            filas.append(profile_file(cfg, path, start=start, duration=duration))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    print(format_table(filas))
    print()
    print(
        "lock/compas: % de frames de render (50 fps) enganchados, tras "
        f"{WARMUP_SECONDS:.0f} s de arranque.  "
        "score: pico de la curva de tempo (no la confianza del reloj).  "
        "hmix/smix: % de frames con harmony_mix>0 y sustain_mix>0."
    )
    return 0
