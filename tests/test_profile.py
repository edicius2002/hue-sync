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

from huebpm.cli.profile import (
    WARMUP_SECONDS,
    ProfileRow,
    format_table,
    profile_file,
    run_profile,
)
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
    assert "offb/s" in out
    assert "on/s" in out
    assert "contratiempo" in out


def test_tabla_separa_onsets_totales_de_contratiempos():
    """Quien calibre onset_delta tiene que ver las dos tasas, no una sola."""
    fila = ProfileRow(
        name="x.wav",
        bpm=120.0,
        clock_lock_pct=100.0,
        tempo_score=0.5,
        bar_lock_pct=10.0,
        bar_conf=0.1,
        tonal_p50=0.0,
        tonal_max=0.0,
        sustain_p50=0.0,
        onsets_per_s=2.0,
        offbeat_per_s=0.9,
        harmony_mix_pct=0.0,
        sustain_mix_pct=0.0,
    )
    tabla = format_table([fila])
    assert "on/s" in tabla
    assert "offb/s" in tabla
    assert "2.00" in tabla
    assert "0.90" in tabla


def test_columnas_de_calibracion_distinguen_click_de_pad(tmp_path):
    """hmix/smix/tonal/onsets no pueden clavarse a cero ni invertirse.

    hmix es la evidencia de la puerta de harmony: si mintiera, la
    recalibracion de otro worker seria falsa y nada lo detectaria.
    """
    click, _ = click_track(120.0, 12.0, SR)
    pad = sustained_pad(12.0, SR)
    fila_click = profile_file(Config(), escribir_wav(tmp_path / "click.wav", click))
    fila_pad = profile_file(Config(), escribir_wav(tmp_path / "pad.wav", pad))

    assert fila_click.harmony_mix_pct == 0.0
    assert fila_pad.harmony_mix_pct > 0.0

    assert fila_click.sustain_mix_pct == 0.0
    assert fila_pad.sustain_mix_pct > 0.0

    assert fila_click.tonal_p50 < 0.05
    assert fila_pad.tonal_p50 > 0.0
    assert fila_pad.tonal_max > 0.0

    assert fila_click.onsets_per_s > 0.0
    assert fila_click.onsets_per_s >= fila_click.offbeat_per_s
    assert fila_pad.onsets_per_s < fila_click.onsets_per_s


def test_warmup_cambia_las_medianas(tmp_path):
    """Sin el salto, chroma y sustain arrancan en cero y bajan el p50 del pad."""
    ruta = escribir_wav(tmp_path / "pad.wav", sustained_pad(12.0, SR))
    cfg = Config()
    con = profile_file(cfg, ruta, warmup=WARMUP_SECONDS)
    sin = profile_file(cfg, ruta, warmup=0.0)
    assert con.sustain_p50 != sin.sustain_p50
    assert con.tonal_p50 != sin.tonal_p50
    assert con.sustain_p50 > sin.sustain_p50
