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
    downbeat_accent: float = 1.0,
    beats_per_bar: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (muestras mono float32, tiempos reales de beat en segundos).

    jitter_ms desplaza cada golpe aleatoriamente, para simular un baterista
    humano en vez de una caja de ritmos.

    downbeat_accent multiplica el bombo del primer tiempo de cada compas. Con
    1.0 todos los tiempos pesan igual y no hay metrica que detectar; subirlo
    genera el ground truth para el seguimiento de compas.
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
            en_downbeat = i % beats_per_bar == 0
            place(kick, t, downbeat_accent if en_downbeat else 1.0)
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


# --- material tonal, para validar el chroma ---------------------------------

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Intervalos en semitonos desde la fundamental.
CHORDS = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "maj7": (0, 4, 7, 11),
    "power": (0, 7),
}


def note_hz(pitch_class: int, octave: int = 4) -> float:
    """Frecuencia de una nota. C4 = 261.6 Hz, A4 = 440 Hz."""
    midi = 12 * (octave + 1) + pitch_class
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def tone(
    freq: float,
    duration: float,
    samplerate: int = 48000,
    harmonics: int = 4,
    decay: float = 0.6,
) -> np.ndarray:
    """Nota con armonicos, no un seno puro.

    Los armonicos importan para que la prueba sea honesta: el tercer armonico
    cae una quinta arriba, o sea en otra clase de altura, asi que un detector
    que solo funcione con senos puros no serviria para instrumentos reales.
    """
    n = int(duration * samplerate)
    t = np.arange(n) / samplerate
    out = np.zeros(n, dtype=np.float32)
    for k in range(1, harmonics + 1):
        if freq * k >= samplerate / 2:
            break
        out += (decay ** (k - 1)) * np.sin(2 * np.pi * freq * k * t).astype(np.float32)
    envelope = np.minimum(1.0, np.arange(n) / max(1, int(0.01 * samplerate)))
    return (out * envelope).astype(np.float32)


def chord(
    root: int,
    quality: str = "maj",
    duration: float = 2.0,
    samplerate: int = 48000,
    octave: int = 3,
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Devuelve (audio, clases de altura presentes)."""
    intervalos = CHORDS[quality]
    n = int(duration * samplerate)
    out = np.zeros(n, dtype=np.float32)
    for semitonos in intervalos:
        pc = (root + semitonos) % 12
        oct_extra = (root + semitonos) // 12
        out += tone(note_hz(pc, octave + oct_extra), duration, samplerate)[:n]
    peak = np.abs(out).max()
    if peak > 0:
        out = out / peak * 0.7
    return out.astype(np.float32), tuple((root + s) % 12 for s in intervalos)


def progression(
    roots,
    quality: str = "maj",
    bar_seconds: float = 2.0,
    samplerate: int = 48000,
) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """Encadena acordes; devuelve el audio y las notas de cada uno."""
    trozos, notas = [], []
    for root in roots:
        audio, pcs = chord(root, quality, bar_seconds, samplerate)
        trozos.append(audio)
        notas.append(pcs)
    return np.concatenate(trozos), notas


# --- ground truth para onsets ------------------------------------------------


def impulse_track(
    times,
    duration: float,
    samplerate: int = 48000,
    noise_level: float = 0.0,
    gains=None,
    seed: int = 0,
) -> np.ndarray:
    """Golpes percusivos en instantes exactos conocidos.

    Es el ground truth mas limpio posible para medir un detector de onsets: se
    sabe al milisegundo donde esta cada golpe, asi que precision y recall son
    numeros, no impresiones.
    """
    rng = np.random.default_rng(seed)
    n = int(duration * samplerate)
    out = np.zeros(n + samplerate, dtype=np.float32)
    golpe = _snare(samplerate)
    for i, t in enumerate(times):
        idx = int(round(t * samplerate))
        gain = 1.0 if gains is None else gains[i]
        if 0 <= idx < n:
            out[idx : idx + len(golpe)] += golpe * gain
    out = out[:n]
    if noise_level:
        out += rng.standard_normal(n).astype(np.float32) * noise_level
    peak = np.abs(out).max()
    if peak > 0:
        out = out / peak * 0.7
    return out.astype(np.float32)
