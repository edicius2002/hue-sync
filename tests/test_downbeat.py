"""Tests del seguimiento de compas.

Incluye una prueba de extremo a extremo con ground truth: se sintetiza un 4/4
con el bombo acentuado en el "1" y se comprueba que el detector encuentra ese
mismo tiempo. Sin esa medida, "detecta el downbeat" seria una afirmacion sin
respaldo, que es justo el error que se cometio calibrando la confianza a ojo.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.downbeat import BarTracker
from huebpm.config import AnalysisConfig, EffectsConfig
from huebpm.effects.base import RenderContext, beat_envelope
from huebpm.engine import AnalysisEngine
from huebpm.state import AudioState
from huebpm.testing.synth import click_track

SR = 48000


# --- BarTracker aislado ------------------------------------------------------


def test_sin_datos_no_hay_enganche():
    bars = BarTracker()
    assert not bars.locked
    assert bars.confidence == 0.0


def test_energia_uniforme_no_engancha():
    """Cuatro tiempos iguales no tienen downbeat. Inventarse uno seria peor
    que admitir que no se sabe."""
    bars = BarTracker()
    for i in range(40):
        bars.push_beat(i, 1.0)
    assert bars.confidence < 0.05
    assert not bars.locked
    assert bars.ambiguous


def test_dos_tiempos_fuertes_iguales_son_ambiguos():
    """El patron mas comun del pop: bombo en 1 y 3. Se conoce la rejilla pero
    no cual de los dos empieza el compas."""
    bars = BarTracker()
    for i in range(60):
        bars.push_beat(i, 5.0 if i % 2 == 0 else 1.0)
    assert bars.locked, "la estructura de 2 tiempos es real"
    assert bars.ambiguous


def test_un_solo_tiempo_dominante_no_es_ambiguo():
    bars = BarTracker()
    for i in range(60):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    assert bars.locked
    assert not bars.ambiguous


def test_encuentra_el_tiempo_acentuado():
    bars = BarTracker()
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 2 else 1.0)
    assert bars.offset == 2
    assert bars.locked


def test_la_confianza_crece_con_el_contraste():
    def confianza(acento):
        bars = BarTracker()
        for i in range(40):
            bars.push_beat(i, acento if i % 4 == 0 else 1.0)
        return bars.confidence

    assert confianza(1.5) < confianza(3.0) < confianza(10.0)


def test_se_readapta_a_un_cambio_de_compas():
    """El decaimiento existe para esto: si la seccion cambia y el acento se
    mueve, el histograma tiene que poder seguirlo."""
    bars = BarTracker(decay=0.85)
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    assert bars.offset == 0
    for i in range(40, 120):
        bars.push_beat(i, 5.0 if i % 4 == 2 else 1.0)
    assert bars.offset == 2


def test_reset_olvida_todo():
    bars = BarTracker()
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    bars.reset()
    assert not bars.locked
    assert bars.scores.sum() == 0.0


def test_beat_in_bar_es_relativo_al_downbeat():
    bars = BarTracker()
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 3 else 1.0)
    assert bars.offset == 3
    assert bars.beat_in_bar(3) == 0
    assert bars.beat_in_bar(4) == 1
    assert bars.beat_in_bar(7) == 0


def test_bar_phase_recorre_el_compas():
    bars = BarTracker(beats_per_bar=4)
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    assert bars.bar_phase(0, 0.0) == pytest.approx(0.0)
    assert bars.bar_phase(1, 0.0) == pytest.approx(0.25)
    assert bars.bar_phase(2, 0.5) == pytest.approx(0.625)
    assert bars.bar_phase(4, 0.0) == pytest.approx(0.0), "vuelve a empezar"


def test_phrase_phase_recorre_la_frase():
    bars = BarTracker(beats_per_bar=4, beats_per_phrase=16)
    for i in range(40):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    assert bars.phrase_phase(0, 0.0) == pytest.approx(0.0)
    assert bars.phrase_phase(8, 0.0) == pytest.approx(0.5)
    assert bars.phrase_phase(16, 0.0) == pytest.approx(0.0)


@pytest.mark.parametrize("indice", range(8))
def test_las_fases_estan_siempre_en_rango(indice):
    bars = BarTracker()
    for i in range(20):
        bars.push_beat(i, 5.0 if i % 4 == 0 else 1.0)
    for fase in (0.0, 0.3, 0.99):
        assert 0.0 <= bars.bar_phase(indice, fase) < 1.0
        assert 0.0 <= bars.phrase_phase(indice, fase) < 1.0


# --- extremo a extremo con audio sintetico -----------------------------------


def analizar(bpm: float, duracion: float, acento: float):
    audio, beat_times = click_track(bpm, duracion, SR, downbeat_accent=acento)
    engine = AnalysisEngine(SR, AnalysisConfig())
    bloque = 256
    for inicio in range(0, len(audio) - bloque, bloque):
        engine.feed(audio[inicio : inicio + bloque], inicio, wall_t=(inicio + bloque) / SR)
    return engine, beat_times


def aciertos_de_downbeat(engine, beat_times) -> tuple[int, int]:
    """Cuenta cuantos downbeats detectados caen en un beat del ground truth
    cuyo indice es multiplo del compas, que es donde esta el acento."""
    aciertos = total = 0
    for indice in range(4, 40):
        if engine.bars.beat_in_bar(indice) != 0:
            continue
        wall = engine.clock.beat_time(indice)
        if wall is None:
            continue
        stream = wall - engine.mapper.offset
        if not (beat_times[0] <= stream <= beat_times[-1]):
            continue
        real = int(np.argmin(np.abs(beat_times - stream)))
        total += 1
        aciertos += real % 4 == 0
    return aciertos, total


def test_detecta_el_downbeat_real_en_audio_sintetico():
    """Ground truth completo: no basta con que el compas sea consistente cada
    4 beats, tiene que caer en el tiempo que de verdad lleva el acento."""
    engine, beat_times = analizar(128.0, 30.0, acento=3.0)
    assert engine.clock.locked
    assert engine.bars.locked, f"confianza {engine.bars.confidence:.3f}"

    aciertos, total = aciertos_de_downbeat(engine, beat_times)
    assert total >= 5, "muy pocos downbeats para medir nada"
    assert aciertos / total >= 0.8, f"solo {aciertos}/{total} caen en el acento real"


def test_la_confianza_crece_con_el_acento_en_audio_real():
    confianzas = [analizar(128.0, 25.0, acento=a)[0].bars.confidence for a in (1.0, 2.0, 4.0)]
    assert confianzas == sorted(confianzas), f"deberia crecer, dio {confianzas}"


def test_sin_acento_detecta_la_rejilla_pero_se_declara_ambiguo():
    """Sin acento el bombo cae en 1 y 3 con la misma fuerza. Hay estructura
    metrica de verdad —esos dos tiempos pesan el triple que los otros— asi que
    negarla seria mentir. Lo que no se puede saber es cual de los dos es el
    "1", y eso es justo lo que reporta `ambiguous`."""
    engine, _ = analizar(128.0, 30.0, acento=1.0)
    assert engine.clock.locked
    assert engine.bars.locked, "la rejilla si esta ahi"
    assert engine.bars.ambiguous, "pero el 1 y el 3 empatan"


def test_con_acento_el_downbeat_deja_de_ser_ambiguo():
    engine, _ = analizar(128.0, 30.0, acento=3.0)
    assert engine.bars.locked
    assert not engine.bars.ambiguous


def test_energia_plana_de_verdad_no_engancha():
    """Cuatro tiempos identicos: no hay nada que detectar y hay que decirlo."""
    bars = BarTracker()
    for i in range(60):
        bars.push_beat(i, 1.0)
    assert not bars.locked


def test_el_histograma_se_reinicia_si_el_reloj_salta():
    engine, _ = analizar(128.0, 20.0, acento=3.0)
    antes = engine.bars.scores.sum()
    assert antes > 0

    engine.clock.reset()
    engine.feed(np.zeros(4096, dtype=np.float32), 10**6, wall_t=1000.0)
    assert engine.bars.scores.sum() == 0.0, "los indices viejos ya no valen"


# --- efectos -----------------------------------------------------------------


def contexto(beat_in_bar: int, fase: float = 0.0, bar_locked: bool = True):
    from huebpm.analysis.beatclock import BeatClock
    from huebpm.analysis.tempo import TempoEstimate

    clock = BeatClock()
    clock.update(TempoEstimate(bpm=120.0, period=0.5, last_beat_time=0.0, confidence=1.0), 0.0)
    return RenderContext(
        now=fase * 0.5,
        state=AudioState(bands=np.array([0.8, 0.3, 0.2]), locked=True),
        clock=clock,
        channel_count=1,
        cfg=EffectsConfig(),
        bar_phase=(beat_in_bar + fase) / 4.0,
        phrase_phase=(beat_in_bar + fase) / 16.0,
        beat_in_bar=beat_in_bar,
        bar_locked=bar_locked,
    )


def test_el_downbeat_pega_mas_fuerte():
    uno = beat_envelope(contexto(0))
    dos = beat_envelope(contexto(1))
    assert uno > dos


def test_sin_enganche_de_compas_todos_los_beats_pesan_igual():
    """Degradar limpiamente importa: acentuar un tiempo al azar se ve peor que
    no acentuar ninguno."""
    valores = {beat_envelope(contexto(i, bar_locked=False)) for i in range(4)}
    assert len(valores) == 1


def test_el_acento_es_configurable():
    ctx = contexto(1)
    sin_acento = RenderContext(
        now=ctx.now, state=ctx.state, clock=ctx.clock, channel_count=1,
        cfg=EffectsConfig(downbeat_accent=0.0),
        beat_in_bar=1, bar_locked=True,
    )
    assert beat_envelope(sin_acento) > beat_envelope(ctx)
