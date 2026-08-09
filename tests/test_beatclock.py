"""Tests del PLL de fase.

Es la pieza de la que depende todo lo demas: si el reloj deriva, no importa lo
bueno que sea el detector de tempo. Se testea sin audio ni bridge, alimentando
estimaciones sinteticas.
"""

from __future__ import annotations

import math

import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate


def estimate(bpm: float, last_beat: float, confidence: float = 1.0) -> TempoEstimate:
    return TempoEstimate(
        bpm=bpm, period=60.0 / bpm, last_beat_time=last_beat, confidence=confidence
    )


def test_no_engancha_sin_estimaciones():
    clock = BeatClock()
    assert not clock.locked
    assert clock.bpm is None
    assert clock.time_to_next_beat(0.0) is None
    assert clock.phase(0.0) == 0.0


def test_engancha_con_la_primera_estimacion():
    clock = BeatClock()
    clock.update(estimate(120.0, 100.0), 100.0)
    assert clock.locked
    assert clock.bpm == pytest.approx(120.0)
    assert clock.period == pytest.approx(0.5)


def test_estimacion_de_baja_confianza_se_descarta():
    clock = BeatClock(min_confidence=0.25)
    clock.update(estimate(120.0, 100.0, confidence=0.1), 100.0)
    assert not clock.locked


def test_time_to_next_beat_siempre_positivo():
    """Nunca debe devolver 0 ni negativo: el efecto lo usa para anticipar, y un
    cero significaria 'el beat es ahora', que ya es tarde."""
    clock = BeatClock()
    clock.update(estimate(120.0, 100.0), 100.0)
    for i in range(200):
        t = 100.0 + i * 0.0137  # paso irracional respecto al periodo
        ttnb = clock.time_to_next_beat(t)
        assert ttnb is not None
        assert 0.0 < ttnb <= clock.period + 1e-9


def test_fase_avanza_y_envuelve():
    clock = BeatClock()
    clock.update(estimate(120.0, 100.0), 100.0)
    assert clock.phase(100.0) == pytest.approx(0.0)
    assert clock.phase(100.25) == pytest.approx(0.5)
    assert clock.phase(100.5) == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= clock.phase(100.37) < 1.0


def test_fase_y_time_to_next_beat_son_coherentes():
    clock = BeatClock()
    clock.update(estimate(140.0, 50.0), 50.0)
    for i in range(50):
        t = 50.0 + i * 0.021
        assert clock.time_to_next_beat(t) == pytest.approx(
            (1.0 - clock.phase(t)) * clock.period, abs=1e-9
        )


def test_poll_beats_cuenta_cada_beat_una_sola_vez():
    clock = BeatClock()
    clock.update(estimate(120.0, 0.0), 0.0)
    clock.poll_beats(0.0)  # primera llamada inicializa

    total = 0
    steps = 400
    for i in range(1, steps + 1):
        total += clock.poll_beats(i * 0.02)  # 8 s a 50 Hz
    # 8 s a 120 BPM = 16 beats.
    assert total == 16


def test_poll_beats_no_pierde_beats_si_el_render_se_atasca():
    clock = BeatClock()
    clock.update(estimate(120.0, 0.0), 0.0)
    clock.poll_beats(0.0)
    # Salto de 2 s de golpe: deben contarse los 4 beats que cabian dentro.
    assert clock.poll_beats(2.0) == 4


def test_el_pll_converge_hacia_la_fase_real():
    """Se arranca el reloj con la fase desplazada y se le dan estimaciones
    correctas: el error debe reducirse de forma sostenida."""
    clock = BeatClock(phase_gain=0.45, period_gain=0.12)
    period = 0.5
    clock.update(estimate(120.0, 0.0 + 0.12), 0.0)  # arranca 120 ms tarde

    errors = []
    for k in range(1, 30):
        t = k * 0.5
        clock.update(estimate(120.0, t), t)
        predicted = clock.time_to_next_beat(t)
        # Distancia al beat real mas cercano, envuelta al periodo.
        err = (predicted + period / 2) % period - period / 2
        errors.append(abs(err))

    assert errors[-1] < errors[0]
    assert errors[-1] < 0.005  # < 5 ms


def test_el_periodo_se_suaviza_no_salta():
    clock = BeatClock(period_gain=0.12)
    clock.update(estimate(120.0, 0.0), 0.0)
    clock.update(estimate(124.0, 0.5), 0.5)
    # Con ganancia 0.12 el periodo se mueve una fraccion, no salta al nuevo.
    assert 60.0 / 124.0 < clock.period < 60.0 / 120.0
    assert clock.period != pytest.approx(60.0 / 124.0)


def test_salto_de_octava_necesita_votos_consecutivos():
    """Un pasaje con el doble de densidad ritmica no debe desenganchar el
    reloj a la primera."""
    clock = BeatClock(octave_snap_count=3)
    clock.update(estimate(120.0, 0.0), 0.0)

    clock.update(estimate(60.0, 1.0), 1.0)
    assert clock.bpm == pytest.approx(120.0, abs=1.0), "no debe saltar con un solo voto"

    clock.update(estimate(60.0, 2.0), 2.0)
    assert clock.bpm == pytest.approx(120.0, abs=1.0)

    clock.update(estimate(60.0, 3.0), 3.0)
    assert clock.bpm == pytest.approx(60.0, abs=1.0), "tras 3 votos si debe saltar"


def test_votos_de_octava_inconsistentes_no_acumulan():
    clock = BeatClock(octave_snap_count=3)
    clock.update(estimate(120.0, 0.0), 0.0)
    for i, bpm in enumerate((60.0, 180.0, 60.0), start=1):
        clock.update(estimate(bpm, float(i)), float(i))
    assert clock.bpm == pytest.approx(120.0, abs=1.0)


def test_is_stale_tras_el_timeout():
    clock = BeatClock(stale_after=3.0)
    assert clock.is_stale(0.0), "sin enganche siempre esta stale"
    clock.update(estimate(120.0, 10.0), 10.0)
    assert not clock.is_stale(11.0)
    assert clock.is_stale(20.0)


def test_reset_desengancha():
    clock = BeatClock()
    clock.update(estimate(120.0, 0.0), 0.0)
    assert clock.locked
    clock.reset()
    assert not clock.locked
    assert clock.bpm is None
    assert clock.confidence == 0.0


def test_el_reloj_corre_libre_sin_actualizaciones():
    """Es el punto del diseno: sin estimaciones nuevas el oscilador sigue
    prediciendo beats en vez de quedarse congelado."""
    clock = BeatClock()
    clock.update(estimate(120.0, 0.0), 0.0)
    lejos = 60.0  # un minuto despues, sin una sola actualizacion
    assert clock.time_to_next_beat(lejos) is not None
    assert clock.phase(lejos) == pytest.approx(0.0, abs=1e-6)
    assert math.isclose(clock.period, 0.5)
