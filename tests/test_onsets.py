"""Tests de deteccion de onsets.

El ground truth es exacto: se sintetizan golpes en instantes conocidos al
milisegundo, asi que precision y recall son numeros medidos y no impresiones.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.odf import SpectralAnalyzer
from huebpm.analysis.onsets import OnsetDetector
from huebpm.config import AnalysisConfig, EffectsConfig
from huebpm.effects.base import RenderContext, onset_accent
from huebpm.engine import AnalysisEngine
from huebpm.state import AudioState
from huebpm.testing.synth import click_track, impulse_track

SR = 48000
TOLERANCIA = 0.05


def detectar(audio: np.ndarray, delta: float = 3.5) -> np.ndarray:
    spec = SpectralAnalyzer(SR)
    det = OnsetDetector(spec.frame_rate, delta=delta)
    encontrados = []
    for s in range(0, len(audio) - 256, 256):
        for f in spec.process(audio[s : s + 256], s):
            onset = det.push(f.flux, f.t)
            if onset is not None:
                encontrados.append(onset.t)
    return np.array(encontrados)


def precision_recall(reales, hallados) -> tuple[float, float]:
    reales = np.asarray(reales)
    if len(hallados) == 0:
        return 0.0, 0.0
    aciertos = sum(1 for r in reales if np.min(np.abs(hallados - r)) < TOLERANCIA)
    falsos = sum(1 for h in hallados if np.min(np.abs(reales - h)) >= TOLERANCIA)
    return aciertos / len(reales), falsos / len(hallados)


# --- deteccion ---------------------------------------------------------------


def test_golpes_regulares():
    tiempos = list(np.arange(0.5, 10.0, 0.5))
    recall, falsos = precision_recall(tiempos, detectar(impulse_track(tiempos, 11.0, SR)))
    assert recall >= 0.9
    assert falsos <= 0.1


def test_golpes_irregulares():
    """Lo que aporta el detector: golpes que NO son periodicos y que el
    seguimiento de tempo, por construccion, descarta."""
    rng = np.random.default_rng(3)
    tiempos = sorted(0.5 + np.cumsum(rng.uniform(0.15, 0.6, 30)))
    recall, falsos = precision_recall(
        tiempos, detectar(impulse_track(tiempos, tiempos[-1] + 1.0, SR))
    )
    assert recall >= 0.9
    assert falsos <= 0.1


def test_aguanta_el_ruido():
    rng = np.random.default_rng(3)
    tiempos = sorted(0.5 + np.cumsum(rng.uniform(0.15, 0.6, 30)))
    audio = impulse_track(tiempos, tiempos[-1] + 1.0, SR, noise_level=0.02)
    recall, falsos = precision_recall(tiempos, detectar(audio))
    assert recall >= 0.9
    assert falsos <= 0.1


def test_el_umbral_gobierna_los_falsos_positivos():
    """Regresion de la calibracion: con umbral bajo, el ruido blanco dispara
    tres veces mas golpes que los que hay."""
    rng = np.random.default_rng(3)
    tiempos = sorted(0.5 + np.cumsum(rng.uniform(0.15, 0.6, 30)))
    audio = impulse_track(tiempos, tiempos[-1] + 1.0, SR, noise_level=0.02)
    _, falsos_bajo = precision_recall(tiempos, detectar(audio, delta=1.0))
    _, falsos_alto = precision_recall(tiempos, detectar(audio, delta=3.5))
    assert falsos_bajo > 0.4
    assert falsos_alto <= 0.1


def test_el_silencio_no_dispara():
    assert len(detectar(np.zeros(SR * 3, dtype=np.float32))) == 0


def test_no_dispara_dos_veces_por_el_mismo_golpe():
    tiempos = [1.0, 3.0, 5.0]
    hallados = detectar(impulse_track(tiempos, 6.5, SR))
    assert len(hallados) <= len(tiempos) + 1


def test_hay_latencia_de_confirmacion_y_es_acotada():
    """No se puede saber que un valor es maximo local hasta ver lo que viene
    despues. Esa espera es latencia pura y conviene tenerla medida."""
    det = OnsetDetector(187.5, lookahead=3)
    assert det.lookahead / 187.5 < 0.03


def test_reset_olvida_el_estado():
    det = OnsetDetector(187.5)
    for i in range(200):
        det.push(1.0 if i == 100 else 0.0, i / 187.5)
    det.reset()
    assert det.push(0.5, 0.0) is None


# --- integracion: solo golpes fuera de tiempo --------------------------------


def test_los_golpes_en_el_pulso_no_generan_acento():
    """Los que caen en el beat ya los cubre la envolvente; acentuarlos otra vez
    solo duplica el mismo destello."""
    audio, _ = click_track(120.0, 25.0, SR)
    engine = AnalysisEngine(SR, AnalysisConfig())
    for s in range(0, len(audio) - 256, 256):
        engine.feed(audio[s : s + 256], s, wall_t=(s + 256) / SR)
    assert engine.clock.locked

    fase = engine.clock.phase(engine.state.last_onset_time)
    if engine.state.last_onset_time > 0:
        distancia = min(fase, 1.0 - fase)
        assert distancia >= AnalysisConfig().onset_offbeat_margin - 0.02


# --- efecto ------------------------------------------------------------------


def contexto(desde_el_golpe: float, fuerza: float = 1.0, cfg=None):
    from huebpm.analysis.beatclock import BeatClock

    return RenderContext(
        now=10.0,
        state=AudioState(
            bands=np.array([0.5, 0.5, 0.5]),
            last_onset_time=10.0 - desde_el_golpe,
            last_onset_strength=fuerza,
        ),
        clock=BeatClock(),
        channel_count=1,
        cfg=cfg or EffectsConfig(),
    )


def test_el_acento_es_maximo_justo_tras_el_golpe():
    assert onset_accent(contexto(0.0)) == pytest.approx(EffectsConfig().onset_accent)


def test_el_acento_decae():
    valores = [onset_accent(contexto(d)) for d in (0.0, 0.05, 0.1, 0.2)]
    assert valores == sorted(valores, reverse=True)


def test_el_acento_se_apaga_del_todo():
    assert onset_accent(contexto(2.0)) == 0.0


def test_sin_golpes_no_hay_acento():
    ctx = RenderContext(
        now=0.0, state=AudioState(), clock=contexto(0.0).clock,
        channel_count=1, cfg=EffectsConfig(),
    )
    assert onset_accent(ctx) == 0.0


def test_la_fuerza_del_golpe_escala_el_acento():
    assert onset_accent(contexto(0.0, 0.3)) < onset_accent(contexto(0.0, 1.0))


def test_se_puede_desactivar():
    cfg = EffectsConfig()
    cfg.onset_accent = 0.0
    assert onset_accent(contexto(0.0, cfg=cfg)) == 0.0


def test_el_acento_no_saca_el_color_de_rango():
    from huebpm.effects.modes import get_effect

    for modo in ("combo", "beat_flash"):
        for c in get_effect(modo).render(contexto(0.0))[0]:
            assert 0.0 <= c <= 1.0


@pytest.mark.parametrize("modo", ["combo", "beat_flash", "bars"])
def test_todos_los_modos_ritmicos_reaccionan_al_onset(modo):
    """Regresion: `combo`, que es el modo por defecto, se quedo sin el codigo
    de onsets porque una sustitucion de texto no encajo y fallo en silencio. El
    PR salio con la feature invisible en el unico modo que la gente usa."""
    from huebpm.effects.modes import get_effect

    efecto = get_effect(modo)
    con = efecto.render(contexto(0.0))[0]
    sin_cfg = EffectsConfig()
    sin_cfg.onset_accent = 0.0
    sin_cfg.onset_flash = 0.0
    sin = efecto.render(contexto(0.0, cfg=sin_cfg))[0]
    distancia = sum((a - b) ** 2 for a, b in zip(con, sin, strict=True)) ** 0.5
    assert distancia > 0.1, f"{modo} no reacciona a los onsets"
