"""Tests del temporizador del loop de render.

Lo que importa es que no acumule deriva: a 50 Hz durante una cancion entera,
un error sistematico de medio milisegundo por tick desplazaria las luces
varios beats. Se testea la aritmetica de planificacion, no la precision real
del sistema operativo, que ya se mide en `sync` y `huetest`.
"""

from __future__ import annotations

import time

import pytest

from huebpm.timing import JitterStats, RateLimiter, TimerResolution, sleep_until


def test_jitter_acumula_media_y_maximo():
    stats = JitterStats()
    for err in (0.001, -0.003, 0.002):
        stats.add(err)
    assert stats.count == 3
    assert stats.mean_ms == pytest.approx(2.0, abs=1e-6)
    assert stats.max_ms == pytest.approx(3.0, abs=1e-6)


def test_jitter_usa_valor_absoluto():
    stats = JitterStats()
    stats.add(-0.005)
    assert stats.max_ms == pytest.approx(5.0)


def test_jitter_vacio():
    stats = JitterStats()
    assert stats.count == 0
    assert stats.mean_ms == 0.0
    assert stats.max_ms == 0.0


def test_intervalo_derivado_de_los_fps():
    assert RateLimiter(50.0).interval == pytest.approx(0.02)
    assert RateLimiter(25.0).interval == pytest.approx(0.04)


def test_el_primer_tick_no_espera():
    limiter = RateLimiter(50.0)
    inicio = time.perf_counter()
    limiter.tick()
    assert time.perf_counter() - inicio < 0.01
    assert limiter.jitter.count == 0, "el primer tick no mide jitter"


def test_no_acumula_deriva():
    """El objetivo real: 40 ticks a 200 Hz deben tardar ~0.2 s en total, sin
    que el error de cada tick se sume al siguiente."""
    limiter = RateLimiter(200.0)
    inicio = time.perf_counter()
    for _ in range(40):
        limiter.tick()
    transcurrido = time.perf_counter() - inicio
    assert transcurrido == pytest.approx(0.2, abs=0.06)


def test_resincroniza_tras_un_atasco():
    """Si el render se atasca mas de un intervalo entero, no debe intentar
    recuperar el tiempo perdido disparando ticks a toda velocidad."""
    limiter = RateLimiter(100.0)
    limiter.tick()
    time.sleep(0.1)  # 10 intervalos de retraso
    limiter.tick()
    inicio = time.perf_counter()
    limiter.tick()
    # El siguiente tick espera un intervalo normal, no vuelve inmediatamente.
    assert time.perf_counter() - inicio > 0.005


def test_sleep_until_no_se_queda_corto():
    objetivo = time.perf_counter() + 0.02
    sleep_until(objetivo)
    assert time.perf_counter() >= objetivo


def test_sleep_until_con_objetivo_pasado_vuelve_ya():
    inicio = time.perf_counter()
    sleep_until(inicio - 1.0)
    assert time.perf_counter() - inicio < 0.005


def test_timer_resolution_es_reentrante_y_seguro():
    """Debe poder usarse como contexto sin romper en ninguna plataforma."""
    with TimerResolution(1):
        pass
    with TimerResolution(1), TimerResolution(1):
        pass
