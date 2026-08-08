"""Generador de audio sintetico con ground truth, para validar el detector.

Sin esto no hay forma honesta de decir si el algoritmo sirve: escuchando a ojo
uno siempre cree que va sincronizado. Aqui se conocen los tiempos exactos de
cada beat, asi que el error de prediccion se mide en milisegundos.

El patron incluye corcheas en el hi-hat a proposito: es justo donde aparecen
los errores de octava (detectar 240 BPM cuando son 120).
"""

from __future__ import annotations

import numpy as np


def _kick(samplerate: int, duration: float = 0.12) -> np.ndarray:
    n = int(samplerate * duration)
    t = np.arange(n) / samplerate
    freq = 120.0 * np.exp(-t * 30.0) + 45.0
    phase = 2 * np.pi * np.cumsum(freq) / samplerate
    return (np.sin(phase) * np.exp(-t * 28.0)).astype(np.float32)


def _hat(samplerate: int, duration: float = 0.04) -> np.ndarray:
    n = int(samplerate * duration)
    t = np.arange(n) / samplerate
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n).astype(np.float32)
    # Diferenciar la senal la vuelve mas brillante: sirve de hi-hat barato.
    noise = np.diff(noise, prepend=0.0)
    return (noise * np.exp(-t * 90.0) * 0.35).astype(np.float32)


def _snare(samplerate: int, duration: float = 0.09) -> np.ndarray:
    n = int(samplerate * duration)
    t = np.arange(n) / samplerate
    rng = np.random.default_rng(13)
    noise = rng.standard_normal(n).astype(np.float32) * 0.5
    tone = np.sin(2 * np.pi * 190.0 * t) * 0.4
    return ((noise + tone) * np.exp(-t * 22.0)).astype(np.float32)


def click_track(
    bpm: float,
    duration: float,
    samplerate: int = 48000,
    jitter_ms: float = 0.0,
    noise_level: float = 0.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (muestras mono float32, tiempos reales de beat en segundos).

    jitter_ms desplaza cada golpe aleatoriamente, para simular un baterista
    humano en vez de una caja de ritmos.
    """
    rng = np.random.default_rng(seed)
    n = int(duration * samplerate)
    out = np.zeros(n + samplerate, dtype=np.float32)

    period = 60.0 / bpm
    beat_times = np.arange(0.0, duration, period)

    kick, snare, hat = _kick(samplerate), _snare(samplerate), _hat(samplerate)

    def place(sample: np.ndarray, t: float, gain: float) -> None:
        idx = int(round(t * samplerate))
        if 0 <= idx < n:
            out[idx : idx + len(sample)] += sample * gain

    for i, bt in enumerate(beat_times):
        offset = rng.normal(0.0, jitter_ms / 1000.0) if jitter_ms else 0.0
        t = bt + offset
        # Patron 4/4: bombo en 1 y 3, caja en 2 y 4.
        if i % 2 == 0:
            place(kick, t, 1.0)
        else:
            place(snare, t, 0.8)
        place(hat, t, 0.5)
        place(hat, t + period / 2.0, 0.35)  # corchea intermedia

    out = out[:n]
    if noise_level:
        out += rng.standard_normal(n).astype(np.float32) * noise_level

    peak = np.abs(out).max()
    if peak > 0:
        out = out / peak * 0.7
    return out.astype(np.float32), beat_times
