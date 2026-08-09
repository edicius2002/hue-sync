"""Tests del ring buffer entre el callback de audio y el hilo de analisis.

El caso que importa es el lector atrasado: si el analisis se retrasa mas que la
capacidad del buffer, tiene que saltar hacia adelante y perder muestras, nunca
devolver datos viejos mezclados con nuevos.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.audio.ringbuffer import RingBuffer


def test_ida_y_vuelta_simple():
    buf = RingBuffer(100)
    datos = np.arange(10, dtype=np.float32)
    buf.write(datos)
    out, idx = buf.read_since(0, 100)
    assert np.array_equal(out, datos)
    assert idx == 10


def test_total_written_es_monotono():
    buf = RingBuffer(50)
    total = 0
    for n in (10, 20, 30, 40):
        buf.write(np.ones(n, dtype=np.float32))
        total += n
        assert buf.total_written == total


def test_wraparound_conserva_el_orden():
    buf = RingBuffer(16)
    buf.write(np.arange(10, dtype=np.float32))
    buf.write(np.arange(10, 20, dtype=np.float32))
    out, _ = buf.read_since(4, 16)
    assert np.array_equal(out, np.arange(4, 20, dtype=np.float32))


def test_lector_atrasado_salta_sin_devolver_basura():
    """Con el lector mas atrasado que la capacidad, debe devolver solo lo que
    sigue siendo valido y reposicionar el indice."""
    buf = RingBuffer(16)
    buf.write(np.arange(40, dtype=np.float32))
    out, idx = buf.read_since(0, 100)
    # Las 24 primeras se perdieron; solo quedan las 16 ultimas.
    assert np.array_equal(out, np.arange(24, 40, dtype=np.float32))
    assert idx == 40


def test_lectura_sin_datos_nuevos_devuelve_vacio():
    buf = RingBuffer(32)
    buf.write(np.arange(8, dtype=np.float32))
    out, idx = buf.read_since(8, 32)
    assert len(out) == 0
    assert idx == 8


def test_max_samples_limita_la_lectura():
    buf = RingBuffer(64)
    buf.write(np.arange(50, dtype=np.float32))
    out, idx = buf.read_since(0, 20)
    assert len(out) == 20
    assert idx == 20
    resto, idx2 = buf.read_since(idx, 100)
    assert np.array_equal(resto, np.arange(20, 50, dtype=np.float32))
    assert idx2 == 50


def test_escritura_mayor_que_el_buffer_conserva_la_cola():
    """Un bloque mas grande que el buffer entero: interesa lo mas reciente."""
    buf = RingBuffer(8)
    buf.write(np.arange(20, dtype=np.float32))
    out, _ = buf.read_since(0, 100)
    assert np.array_equal(out, np.arange(12, 20, dtype=np.float32))
    assert buf.total_written == 20


def test_lectura_continua_no_pierde_ni_duplica():
    """Simula el patron real: escrituras de 256 y lecturas periodicas."""
    buf = RingBuffer(4096)
    idx = 0
    recibido = []
    valor = 0
    for _ in range(30):
        bloque = np.arange(valor, valor + 256, dtype=np.float32)
        valor += 256
        buf.write(bloque)
        out, idx = buf.read_since(idx, 4096)
        recibido.append(out)
    todo = np.concatenate(recibido)
    assert np.array_equal(todo, np.arange(valor, dtype=np.float32))


def test_buffer_vacio_no_revienta():
    buf = RingBuffer(16)
    out, idx = buf.read_since(0, 16)
    assert len(out) == 0
    assert idx == 0


def test_escritura_vacia_es_inocua():
    buf = RingBuffer(16)
    buf.write(np.arange(4, dtype=np.float32))
    buf.write(np.empty(0, dtype=np.float32))
    assert buf.total_written == 4
    out, _ = buf.read_since(0, 16)
    assert np.array_equal(out, np.arange(4, dtype=np.float32))


def test_dtype_se_conserva():
    buf = RingBuffer(32)
    buf.write(np.ones(8, dtype=np.float32) * 0.5)
    out, _ = buf.read_since(0, 32)
    assert out.dtype == np.float32
    assert out == pytest.approx(0.5)
