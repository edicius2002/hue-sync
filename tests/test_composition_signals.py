"""Senales de composicion publicadas por el motor.

Las pruebas usan audio y frames sinteticos porque cada magnitud tiene ground
truth exacto: asi se prueba la semantica DSP sin depender del bridge ni de una
tarjeta de sonido.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.odf import Frame, SpectralAnalyzer
from huebpm.analysis.onsets import Onset
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import AnalysisConfig
from huebpm.engine import AnalysisEngine

SR = 48000


def _tono(freq: float, duration: float = 1.0) -> np.ndarray:
    t = np.arange(int(SR * duration)) / SR
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _frames(audio: np.ndarray) -> list[Frame]:
    analyzer = SpectralAnalyzer(SR)
    frames = []
    for start in range(0, len(audio) - analyzer.hop, analyzer.hop):
        frames.extend(analyzer.process(audio[start : start + analyzer.hop], start))
    return frames


def test_la_fft_expone_subgrave_20_a_80_hz_sin_cambiar_las_tres_bandas():
    subgrave = _frames(_tono(50.0))
    bajo = _frames(_tono(160.0))

    assert hasattr(subgrave[-1], "sub_bass")
    assert subgrave[-1].bands.shape == (3,)
    nivel_subgrave = np.mean([frame.sub_bass for frame in subgrave[20:]])
    nivel_bajo = np.mean([frame.sub_bass for frame in bajo[20:]])
    assert nivel_subgrave > nivel_bajo * 4.0


def _engine_con_reloj() -> AnalysisEngine:
    engine = AnalysisEngine(SR, AnalysisConfig())
    engine.clock.update(
        TempoEstimate(bpm=120.0, period=0.5, last_beat_time=0.0, confidence=1.0),
        now=0.0,
    )
    return engine


def _frame(t: float, low: float) -> Frame:
    return Frame(0, t, 0.0, 0.0, np.array([low, 0.0, 0.0]))


def test_la_fuerza_cierra_el_beat_y_olvida_la_rejilla_anterior():
    engine = _engine_con_reloj()
    engine._accumulate_beat_energy([_frame(0.10, 0.8), _frame(0.35, 0.4)])
    engine._accumulate_beat_energy([_frame(0.51, 0.2)])
    primer_beat = engine._beat_strength
    assert primer_beat == pytest.approx(1.0)

    engine.clock.reset()
    engine._accumulate_beat_energy([_frame(1.10, 0.9)])
    assert engine._beat_strength == 0.0


def test_la_tasa_cuenta_antes_de_descartar_los_golpes_en_el_pulso():
    engine = _engine_con_reloj()

    class DetectorEnElPulso:
        def push(self, _flux: float, t: float) -> Onset:
            return Onset(t=t, strength=1.0)

    engine.onsets = DetectorEnElPulso()  # type: ignore[assignment]
    engine._detect_onsets([_frame(0.0, 0.0), _frame(0.5, 0.0), _frame(1.0, 0.0)])

    # Los tres caen exactamente en beats: no son acentos, pero si densidad.
    assert engine._last_onset_time == -1e9
    assert engine._onset_rate == pytest.approx(1.5)


def test_el_motor_publica_las_tres_senales_en_el_estado():
    engine = _engine_con_reloj()

    class DetectorSiempre:
        def push(self, _flux: float, t: float) -> Onset:
            return Onset(t=t, strength=1.0)

    engine.onsets = DetectorSiempre()  # type: ignore[assignment]
    audio = _tono(50.0, 1.2)
    for start in range(0, len(audio) - 256, 256):
        engine.feed(audio[start : start + 256], start, wall_t=(start + 256) / SR)

    state = engine.state
    assert state.sub_bass > 0.5
    assert state.beat_strength > 0.0
    assert state.onset_rate > 0.0
