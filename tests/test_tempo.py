"""Tests del estimador de tempo.

El `selftest` ya valida la precision de extremo a extremo sobre señal
sintetica. Aqui se cubren las piezas internas y los bordes que aquel no toca:
historia parcial, silencio, y las decisiones de scoring que costaron encontrar.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.tempo import TempoTracker, _moving_average

FRAME_RATE = 187.5


def tracker(**kwargs) -> TempoTracker:
    base = dict(frame_rate=FRAME_RATE, history_seconds=6.0, min_history_seconds=3.0)
    base.update(kwargs)
    return TempoTracker(**base)


def alimentar_pulsos(tr: TempoTracker, bpm: float, segundos: float, amplitud: float = 1.0):
    """Mete un tren de impulsos al ritmo pedido, como haria la ODF."""
    periodo = 60.0 / bpm * FRAME_RATE
    total = int(segundos * FRAME_RATE)
    for i in range(total):
        cerca_del_pulso = (i % periodo) < 1.0
        tr.push(amplitud if cerca_del_pulso else 0.0, i / FRAME_RATE)


def test_media_movil_de_constante_es_la_constante():
    x = np.full(100, 3.0)
    assert _moving_average(x, 11) == pytest.approx(np.full(100, 3.0))


def test_media_movil_conserva_la_longitud():
    for ancho in (2, 5, 33, 101):
        assert len(_moving_average(np.random.rand(200), ancho)) == 200


def test_media_movil_con_ancho_degenerado_da_ceros():
    assert _moving_average(np.random.rand(20), 1) == pytest.approx(np.zeros(20))


def test_no_esta_listo_antes_de_la_historia_minima():
    tr = tracker()
    assert not tr.ready
    for i in range(int(2.0 * FRAME_RATE)):
        tr.push(0.5, i / FRAME_RATE)
    assert not tr.ready, "2 s < min_history_seconds"
    assert tr.estimate() is None


def test_listo_con_historia_parcial():
    """No hace falta llenar los 6 s: esperar impone un suelo duro al enganche."""
    tr = tracker()
    for i in range(int(3.1 * FRAME_RATE)):
        tr.push(0.5, i / FRAME_RATE)
    assert tr.ready


def test_silencio_no_produce_estimacion():
    tr = tracker()
    for i in range(int(6.5 * FRAME_RATE)):
        tr.push(0.0, i / FRAME_RATE)
    assert tr.estimate() is None


@pytest.mark.parametrize("bpm", [90.0, 120.0, 140.0])
def test_detecta_periodicidad_sintetica(bpm):
    tr = tracker()
    alimentar_pulsos(tr, bpm, 7.0)
    est = tr.estimate()
    assert est is not None
    # Puede engancharse a una octava; lo que no vale es una relacion no entera.
    ratio = est.bpm / bpm
    assert abs(round(np.log2(ratio)) - np.log2(ratio)) < 0.05


def test_la_confianza_esta_acotada():
    tr = tracker()
    alimentar_pulsos(tr, 120.0, 7.0)
    est = tr.estimate()
    assert est is not None
    assert 0.0 <= est.confidence <= 1.0


def test_ruido_sin_pulso_da_baja_confianza():
    """Ruido blanco no tiene periodicidad: la confianza debe quedar muy por
    debajo de la de un pulso limpio."""
    rng = np.random.default_rng(0)
    ruidoso = tracker()
    for i in range(int(7.0 * FRAME_RATE)):
        ruidoso.push(float(rng.random()), i / FRAME_RATE)
    limpio = tracker()
    alimentar_pulsos(limpio, 120.0, 7.0)

    est_ruido, est_limpio = ruidoso.estimate(), limpio.estimate()
    assert est_limpio is not None
    if est_ruido is not None:
        assert est_ruido.confidence < est_limpio.confidence


def test_el_periodo_y_el_bpm_son_coherentes():
    tr = tracker()
    alimentar_pulsos(tr, 128.0, 7.0)
    est = tr.estimate()
    assert est is not None
    assert est.period == pytest.approx(60.0 / est.bpm)


def test_el_ultimo_beat_cae_dentro_de_la_ventana():
    tr = tracker()
    alimentar_pulsos(tr, 120.0, 7.0)
    est = tr.estimate()
    assert est is not None
    ahora = tr._last_t
    assert ahora - est.period - 1e-6 <= est.last_beat_time <= ahora + 1e-6


def test_el_tempo_se_mantiene_dentro_del_rango_configurado():
    tr = tracker(min_bpm=100.0, max_bpm=140.0)
    alimentar_pulsos(tr, 120.0, 7.0)
    est = tr.estimate()
    assert est is not None
    assert 100.0 <= est.bpm <= 140.0


def test_la_curva_de_puntuacion_es_inspeccionable():
    """`score_curve` es publica a proposito: sin ella no hay forma de entender
    por que el detector eligio un tempo."""
    tr = tracker()
    alimentar_pulsos(tr, 120.0, 7.0)
    curva = tr.score_curve()
    assert curva is not None
    assert len(curva.lags) == len(curva.bpms) == len(curva.final)
    assert curva.bpms.min() >= tr.min_bpm - 1
    assert curva.bpms.max() <= tr.max_bpm + 5
    assert 0.0 <= curva.salience(10.0) <= 1.0


def test_la_normalizacion_es_invariante_al_volumen():
    """El mismo ritmo mas flojo debe dar el mismo tempo: es lo que consigue la
    resta de la media movil."""
    fuerte, flojo = tracker(), tracker()
    alimentar_pulsos(fuerte, 120.0, 7.0, amplitud=1.0)
    alimentar_pulsos(flojo, 120.0, 7.0, amplitud=0.02)
    e1, e2 = fuerte.estimate(), flojo.estimate()
    assert e1 is not None and e2 is not None
    assert e1.bpm == pytest.approx(e2.bpm, abs=0.5)
