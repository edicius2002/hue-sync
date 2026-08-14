"""Analisis offline de un WAV, con volcado de diagnostico.

Reproduce exactamente el camino en vivo (mismos bloques, mismo motor) pero de
forma determinista y repetible, y ademas ensena *por que* el detector eligio un
tempo: la curva de puntuacion por candidato.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from ..config import Config
from ..effects.base import RenderContext, sustain_mix
from ..engine import AnalysisEngine
from ..testing.synth import NOTE_NAMES


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as fh:
        rate = fh.getframerate()
        channels = fh.getnchannels()
        width = fh.getsampwidth()
        raw = fh.readframes(fh.getnframes())

    if width != 2:
        raise ValueError(f"Solo se admite WAV de 16 bits, este tiene {width * 8}")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def run_analyze(
    cfg: Config,
    path: Path,
    expected_bpm: float | None = None,
    start: float = 0.0,
    duration: float | None = None,
) -> int:
    audio, rate = load_wav(path)
    if start or duration:
        # Recortar sirve para separar dos cosas que se confunden: que el
        # detector falle, o que ese tramo del tema tenga otro pulso (intros,
        # breakdowns). Analizar desde despues de la intro lo resuelve.
        begin = int(start * rate)
        end = begin + int(duration * rate) if duration else len(audio)
        audio = audio[begin:end]
        print(f"(recorte: desde {start:.1f} s, {len(audio) / rate:.1f} s de audio)")
    print(f"{path.name}: {len(audio) / rate:.1f} s a {rate} Hz, "
          f"pico {np.abs(audio).max():.3f}, RMS {np.sqrt(np.mean(audio ** 2)):.4f}")

    engine = AnalysisEngine(rate, cfg.analysis)
    block = cfg.audio.blocksize

    print(f"\n{'t':>6} {'tracker':>9} {'conf':>6} {'acf':>6} {'reloj':>8} "
          f"{'bconf':>6} {'nota':>5} {'tonal':>6} {'sosten':>6} {'mezcla':>6}  {'envolvente':<12}")
    trace_at = 0.0
    lock_time = None
    settled_at = None
    last_bpm = None
    sustain_samples = []
    mix_samples = []
    for offset in range(0, len(audio) - block, block):
        t = (offset + block) / rate
        engine.feed(audio[offset : offset + block], offset, wall_t=t)
        state = engine.state
        sustain_samples.append(state.sustain)
        mix_frame = sustain_mix(
            RenderContext(
                now=t,
                state=state,
                clock=engine.clock,
                channel_count=1,
                cfg=cfg.effects,
            )
        )
        mix_samples.append(mix_frame)
        if lock_time is None and engine.clock.locked:
            lock_time = t
        # "Estable" = ultima vez que el tempo del reloj salto mas de un 2%. Es
        # el numero que importa de verdad, no el primer enganche: enganchar
        # rapido a un tempo equivocado no sirve de nada.
        bpm_now = engine.clock.bpm
        if bpm_now is not None:
            if last_bpm is None or abs(np.log2(bpm_now / last_bpm)) > 0.03:
                settled_at = t
            last_bpm = bpm_now
        if t >= trace_at and engine.tempo.ready:
            trace_at = t + 1.0
            est = engine.tempo.estimate()
            curve = engine.tempo.score_curve()
            acf = f"{curve.raw.max():6.3f}" if curve is not None else "    --"
            if est:
                clock = f"{engine.clock.bpm:8.1f}" if engine.clock.bpm else "      --"
                sustain = state.sustain
                barra = "#" * int(round(sustain * 12))
                print(f"{t:6.1f} {est.bpm:9.1f} {est.confidence:6.2f} {acf} {clock} "
                      f"{engine.bars.confidence:6.2f} "
                      f"{NOTE_NAMES[engine.chroma.dominant]:>5} "
                      f"{engine.chroma.tonality:6.3f} {sustain:6.3f} {mix_frame:6.3f}  "
                      f"{barra:<12}")

    if lock_time:
        print(f"\nPrimer enganche a los {lock_time:.1f} s")
        if settled_at is not None:
            print(f"Tempo estable desde los {settled_at:.1f} s")
    else:
        print("\nNunca engancho")
    if engine.clock.bpm:
        print(f"BPM final: {engine.clock.bpm:.1f}   confianza {engine.clock.confidence:.2f}")
        if expected_bpm:
            ratio = engine.clock.bpm / expected_bpm
            octave = abs(round(np.log2(ratio)) - np.log2(ratio)) < 0.04
            print(f"Esperado {expected_bpm:.1f}  ->  x{ratio:.3f}  "
                  f"{'octava valida' if octave else 'RELACION NO ENTERA'}")

    sustain = np.asarray(sustain_samples)
    if len(sustain):
        mezclas = np.asarray(mix_samples)
        low = float(np.mean(sustain < 0.05))
        high = float(np.mean(sustain > 0.95))
        useful = float(np.mean((sustain >= 0.35) & (sustain <= 0.65)))
        print(f"\nSostenimiento: media {sustain.mean():.3f}, minimo {sustain.min():.3f}, "
              f"maximo {sustain.max():.3f}")
        print(f"  bajo <0.05: {low:5.1%}   alto >0.95: {high:5.1%}   "
              f"banda util 0.35-0.65: {useful:5.1%}")
        print("  referencia: sostenimiento alto = envolvente estable; mezcla >0 entra al modo")
        print(f"Mezcla efectiva: media {mezclas.mean():.3f}, maximo {mezclas.max():.3f}, "
              f"activa >0: {np.mean(mezclas > 0):5.1%}")

    bars = engine.bars
    print(f"\nCompas: confianza {bars.confidence:.3f} "
          f"(umbral {bars.min_confidence:.2f}) -> "
          f"{'ENGANCHADO en el tiempo ' + str(bars.offset) if bars.locked else 'sin enganche'}"
          f"{'  [AMBIGUO: el 1 y el 3 empatan, puede ir medio compas desplazado]' if bars.locked and bars.ambiguous else ''}")
    total = bars.scores.sum()
    if total > 0:
        reparto = bars.scores / total
        for i, peso in enumerate(reparto):
            marca = " <- el '1'" if i == bars.offset else ""
            print(f"  tiempo {i}: {peso:5.1%}  {'#' * int(peso * 60)}{marca}")
        print("  (un reparto plano de 25% significa que no hay metrica detectable)")

    ch = engine.chroma
    print(f"\nArmonia: tonalidad {ch.tonality:.3f}, nota dominante "
          f"{NOTE_NAMES[ch.dominant]}, hue {ch.hue:.3f}")
    print("  referencia:  ~0.01 ruido   ~0.04 mezcla densa   >0.15 material tonal")
    reparto = ch.chroma / max(ch.chroma.sum(), 1e-9)
    for i in np.argsort(reparto)[::-1][:6]:
        print(f"  {NOTE_NAMES[i]:>2}: {reparto[i]:5.1%}  {'#' * int(reparto[i] * 100)}")

    curve = engine.tempo.score_curve()
    if curve is not None:
        print(f"\nCandidatos al final:\n{'bpm':>7} {'lag':>5} {'acf':>8} "
              f"{'+arm':>8} {'prior':>7} {'final':>8}")
        for i in np.argsort(curve.final)[::-1][:8]:
            print(f"{curve.bpms[i]:7.1f} {curve.lags[i]:5d} {curve.raw[i]:8.3f} "
                  f"{curve.harmonic[i]:8.3f} {curve.prior[i]:7.3f} {curve.final[i]:8.3f}")
        median = float(np.median(curve.raw))
        mad = float(np.median(np.abs(curve.raw - median)))
        print(f"\nFondo de la curva: mediana {median:.3f}, MAD {mad:.3f}  ->  "
              f"z del pico = {(curve.raw.max() - median) / (1.4826 * mad + 1e-9):.1f}")
        print(f"(la confianza es z / salience_scale, ahora {cfg.analysis.salience_scale:.0f})")
    return 0
