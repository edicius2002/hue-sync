"""Captura loopback a WAV mono.

Existe para poder afinar el detector contra material real de forma repetible:
el mismo fragmento analizado N veces con parametros distintos, en vez de
ajustar a ojo mientras suena algo que no se puede volver a reproducir igual.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np

from ..audio.capture import LoopbackCapture, resolve_device
from ..config import Config


def run_record(cfg: Config, out_path: Path, seconds: float) -> int:
    device = resolve_device(cfg.audio.device_index, cfg.audio.device_name)
    print(f"Dispositivo: [{device.index}] {device.name}")
    print(f"Grabando {seconds:.0f} s a {out_path} ... pon la musica ahora.")

    capture = LoopbackCapture(
        device=device,
        blocksize=cfg.audio.blocksize,
        buffer_seconds=max(cfg.audio.buffer_seconds, seconds + 2.0),
    )

    capture.start()
    try:
        start = capture.buffer.total_written
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(0.1)
            got = (capture.buffer.total_written - start) / device.samplerate
            print(f"\r  {got:5.1f} / {seconds:.0f} s", end="", flush=True)
        samples, _ = capture.buffer.read_since(start, int(seconds * device.samplerate) + 1)
    finally:
        capture.stop()
    print()

    if len(samples) == 0:
        print("No llego audio. Revisa 'run.py devices' y audio.device_index.")
        return 1

    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(out_path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(device.samplerate)
        fh.writeframes(pcm.tobytes())

    peak = float(np.abs(samples).max())
    print(f"Guardado: {out_path}  ({len(samples) / device.samplerate:.1f} s, "
          f"{device.samplerate} Hz, pico {peak:.3f})")
    if peak < 0.01:
        print("AVISO: el pico es casi cero. El dispositivo capturo silencio.")
    return 0
