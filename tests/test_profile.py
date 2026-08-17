"""Tests del subcomando profile: tabla cruzada, un motor por fichero.

Sin WAV reales: se sintetizan con ground truth. El caso que de verdad
protege esto es mezclar dos temas en el mismo AnalysisEngine — el histograma
de compas del primero se cuela en el segundo y las filas mienten.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from huebpm.cli.profile import ProfileRow, profile_file, run_profile
from huebpm.config import Config
from huebpm.testing.synth import click_track, concatenate_sections, sustained_pad

SR = 48000


def escribir_wav(path: Path, audio: np.ndarray, rate: int = SR) -> Path:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(pcm.tobytes())
    return path


def test_click_track_reporta_el_bpm_conocido(tmp_path):
    audio, _ = click_track(120.0, 12.0, SR)
    ruta = escribir_wav(tmp_path / "click120.wav", audio)
    fila = profile_file(Config(), ruta)
    assert fila.bpm is not None
    assert fila.bpm == pytest.approx(120.0, abs=2.0)


def test_dos_ficheros_no_mezclan_estadisticas(tmp_path):
    """Si se reusa el motor, el histograma de compas del click contamina el pad.

    Un AnalysisEngine arrastra PLL, BarTracker y el ultimo onset. El pad
    aislado casi no engancha compas (bar_lock < 25%). Si se comparte el motor,
    el lock del click se queda y la fila del pad marca ~50%.
    """
    click, _ = click_track(120.0, 12.0, SR)
    pad = sustained_pad(12.0, SR)
    a = escribir_wav(tmp_path / "click.wav", click)
    b = escribir_wav(tmp_path / "pad.wav", pad)
    cfg = Config()
    fila_click = profile_file(cfg, a)
    fila_pad = profile_file(cfg, b)
    assert fila_click.bpm == pytest.approx(120.0, abs=2.0)
    # El pad aislado casi no engancha compas. Si el motor se reusa, el
    # histograma del click deja bar_lock por encima del 50%.
    assert fila_pad.bar_lock_pct < 25.0
    assert fila_pad.sustain_p50 > fila_click.sustain_p50 + 0.2
    assert fila_click.name == "click.wav"
    assert fila_pad.name == "pad.wav"


def test_start_y_duration_recortan_de_verdad(tmp_path):
    lento, _ = click_track(100.0, 8.0, SR)
    rapido, _ = click_track(140.0, 8.0, SR)
    mezcla = concatenate_sections(lento, rapido)
    ruta = escribir_wav(tmp_path / "dos_tempos.wav", mezcla)
    cfg = Config()
    primera = profile_file(cfg, ruta, start=0.0, duration=8.0)
    segunda = profile_file(cfg, ruta, start=8.0, duration=8.0)
    assert primera.bpm == pytest.approx(100.0, abs=3.0)
    assert segunda.bpm == pytest.approx(140.0, abs=3.0)


def test_fichero_inexistente_da_error_claro_sin_traceback(tmp_path, capsys):
    inexistente = tmp_path / "no_existe.wav"
    codigo = run_profile(Config(), [inexistente])
    assert codigo == 1
    err = capsys.readouterr().err
    assert "no_existe.wav" in err
    assert "Traceback" not in err


def test_run_profile_imprime_una_fila_por_fichero(tmp_path, capsys):
    uno, _ = click_track(120.0, 10.0, SR)
    dos, _ = click_track(90.0, 10.0, SR)
    a = escribir_wav(tmp_path / "a.wav", uno)
    b = escribir_wav(tmp_path / "b.wav", dos)
    codigo = run_profile(Config(), [a, b])
    assert codigo == 0
    out = capsys.readouterr().out
    assert "a.wav" in out
    assert "b.wav" in out
    assert out.index("a.wav") < out.index("b.wav")


def test_profile_file_devuelve_fila_con_campos(tmp_path):
    audio, _ = click_track(120.0, 10.0, SR)
    ruta = escribir_wav(tmp_path / "x.wav", audio)
    fila = profile_file(Config(), ruta)
    assert isinstance(fila, ProfileRow)
    assert fila.clock_lock_pct >= 0.0
    assert fila.bar_lock_pct >= 0.0
    assert fila.onsets_per_s >= 0.0
