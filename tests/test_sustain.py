"""Pruebas numericas del detector de sostenimiento."""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.odf import Frame, SpectralAnalyzer
from huebpm.analysis.sustain import SustainDetector
from huebpm.testing.synth import (
    click_track,
    concatenate_sections,
    pad_and_drums,
    sustained_pad,
)

SR = 48000


def medir(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    spec = SpectralAnalyzer(SR)
    detector = SustainDetector(spec.frame_rate)
    tiempos, valores = [], []
    for start in range(0, len(audio) - spec.hop, spec.hop):
        for frame in spec.process(audio[start : start + spec.hop], start):
            tiempos.append(frame.t)
            valores.append(detector.push(frame))
    return np.array(tiempos), np.array(valores)


def valor_en(tiempos: np.ndarray, valores: np.ndarray, t: float) -> float:
    return float(valores[np.searchsorted(tiempos, t, side="right") - 1])


def media_final(audio: np.ndarray) -> float:
    _, valores = medir(audio)
    return float(np.mean(valores[-SR // 256 :]))


def test_separa_pad_de_percusion():
    pad = media_final(sustained_pad(12.0, SR))
    bateria = media_final(click_track(120.0, 12.0, SR)[0])
    assert pad > 0.85
    assert bateria < 0.10


def test_el_ruido_continuo_puntua_alto():
    """La tonalidad es puerta del efecto: una envolvente de ruido estable cuenta."""
    ruido = np.random.default_rng(4).normal(0.0, 0.15, SR * 12).astype(np.float32)
    assert media_final(ruido) > 0.85


def test_la_mezcla_queda_entre_los_extremos():
    pad = media_final(sustained_pad(12.0, SR))
    mezcla = media_final(pad_and_drums(12.0, samplerate=SR))
    bateria = media_final(click_track(120.0, 12.0, SR)[0])
    assert bateria < mezcla < pad
    assert 0.60 < mezcla < 0.80


def test_el_barrido_de_bateria_da_una_rampa_decreciente():
    ganancias = (0.75, 0.80, 0.85, 0.90, 0.95)
    valores = [
        media_final(pad_and_drums(12.0, samplerate=SR, drum_gain=ganancia))
        for ganancia in ganancias
    ]
    assert all(0.35 < valor < 0.65 for valor in valores)
    assert valores == sorted(valores, reverse=True)
    assert valores[0] - valores[-1] > 0.15


def test_conmuta_en_3_25_segundos():
    seccion = 7.0
    audio = concatenate_sections(
        click_track(120.0, seccion, SR)[0], sustained_pad(seccion, SR)
    )
    tiempos, valores = medir(audio)
    assert valor_en(tiempos, valores, seccion - 0.1) < 0.25
    assert valor_en(tiempos, valores, seccion + 3.25) > 0.50


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"frame_rate": 0.0}, "frame_rate"),
        ({"frame_rate": 187.5, "window": 0.0}, "window"),
        ({"frame_rate": 187.5, "transition": 0.0}, "transition"),
        ({"frame_rate": 187.5, "energy_full": -0.1}, "energy_full"),
        ({"frame_rate": 187.5, "energy_full": 0.4, "energy_zero": 0.3}, "energy_zero"),
    ],
)
def test_rechaza_parametros_invalidos(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SustainDetector(**kwargs)


def test_reset_olvida_la_ventana():
    detector = SustainDetector(187.5)
    for i in range(600):
        detector.push(
            # Un frame constante simula una envolvente que ya se estabilizo.
            Frame(i, i / 187.5, 0.0, 0.0, np.ones(3))
        )
    detector.reset()
    assert detector.push(
        Frame(0, 0.0, 0.0, 0.0, np.ones(3))
    ) == pytest.approx(0.0)
