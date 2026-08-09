"""Tests de la envolvente del beat y de los modos de color.

La envolvente es lo que hace que la luz se anticipe al ritmo, asi que aqui se
verifica explicitamente que sube ANTES del golpe y que no tiene escalones: un
salto a la baja justo antes del beat se ve como un parpadeo raro.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext, beat_envelope, fill, saturate, spectrum_color
from huebpm.effects.modes import EFFECTS, get_effect
from huebpm.state import AudioState

PERIOD = 0.5
ANCHOR = 100.0


def make_ctx(phase: float, bands=(0.9, 0.3, 0.1), locked: bool = True, cfg=None):
    cfg = cfg or EffectsConfig()
    clock = BeatClock()
    if locked:
        clock.update(
            TempoEstimate(bpm=120.0, period=PERIOD, last_beat_time=ANCHOR, confidence=1.0),
            ANCHOR,
        )
    state = AudioState(bands=np.array(bands), locked=locked)
    return RenderContext(
        now=ANCHOR + phase * PERIOD,
        state=state,
        clock=clock,
        channel_count=1,
        cfg=cfg,
    )


def test_envolvente_maxima_en_el_golpe():
    assert beat_envelope(make_ctx(0.0)) == pytest.approx(1.0)


def test_envolvente_decae_tras_el_golpe():
    valores = [beat_envelope(make_ctx(p)) for p in (0.0, 0.1, 0.2, 0.4)]
    assert valores == sorted(valores, reverse=True)


def test_envolvente_sube_antes_del_golpe():
    """La anticipacion: en el tramo final la envolvente crece hacia el beat que
    todavia no ha sonado. Sin esto el efecto solo puede reaccionar."""
    cfg = EffectsConfig()
    inicio_rampa = 1.0 - cfg.beat_attack
    antes = beat_envelope(make_ctx(inicio_rampa + 0.001))
    despues = beat_envelope(make_ctx(0.999))
    assert despues > antes


def test_envolvente_continua_en_el_arranque_de_la_rampa():
    """Regresion: la rampa arrancaba en cero y producia un escalon a la baja
    justo antes de subir hacia el golpe."""
    cfg = EffectsConfig()
    borde = 1.0 - cfg.beat_attack
    # Epsilon pequeño a proposito: la rampa sube de 0 a 1 en solo `beat_attack`
    # de fase, asi que con un epsilon grande la propia pendiente legitima se
    # confundiria con un escalon.
    eps = 1e-6
    izquierda = beat_envelope(make_ctx(borde - eps))
    derecha = beat_envelope(make_ctx(borde + eps))
    assert derecha == pytest.approx(izquierda, abs=1e-4)


def test_envolvente_sin_saltos_en_todo_el_beat():
    cfg = EffectsConfig()
    fases = np.linspace(0.0, 1.0, 2001)
    valores = np.array([beat_envelope(make_ctx(float(p), cfg=cfg)) for p in fases])
    saltos = np.abs(np.diff(valores))
    # Se excluye el reinicio en el golpe, que es discontinuo por definicion.
    assert saltos[:-1].max() < 0.05


def test_envolvente_respeta_el_suelo():
    cfg = EffectsConfig(beat_floor=0.3)
    for p in np.linspace(0.0, 0.999, 200):
        assert beat_envelope(make_ctx(float(p), cfg=cfg)) >= 0.3 - 1e-9


def test_envolvente_acotada_a_uno():
    for p in np.linspace(0.0, 0.999, 200):
        assert 0.0 <= beat_envelope(make_ctx(float(p))) <= 1.0


def test_sin_enganche_devuelve_el_suelo():
    """Sin pulso claro la luz se queda tenue y fija, no a oscuras ni
    parpadeando al azar."""
    cfg = EffectsConfig(beat_floor=0.2)
    assert beat_envelope(make_ctx(0.5, locked=False, cfg=cfg)) == pytest.approx(0.2)


def test_color_sigue_a_la_banda_dominante():
    cfg = EffectsConfig()
    graves = spectrum_color(make_ctx(0.0, bands=(1.0, 0.0, 0.0), cfg=cfg))
    agudos = spectrum_color(make_ctx(0.0, bands=(0.0, 0.0, 1.0), cfg=cfg))
    assert graves[0] > graves[2], "graves dominantes -> tira a rojo"
    assert agudos[2] > agudos[0], "agudos dominantes -> tira a azul"


def test_color_sin_energia_cae_al_de_reposo():
    cfg = EffectsConfig()
    assert spectrum_color(make_ctx(0.0, bands=(0.0, 0.0, 0.0), cfg=cfg)) == cfg.idle_color


def test_saturate_aleja_del_gris():
    gris = (0.5, 0.5, 0.5)
    assert saturate(gris, 1.5) == pytest.approx(gris), "el gris puro no tiene direccion"
    color = (0.6, 0.5, 0.4)
    sat = saturate(color, 1.5)
    assert sat[0] > color[0] and sat[2] < color[2]


def test_saturate_no_se_sale_de_rango():
    for boost in (1.0, 1.15, 3.0):
        for c in saturate((0.95, 0.5, 0.02), boost):
            assert 0.0 <= c <= 1.0


def test_fill_replica_en_todos_los_canales():
    canales = fill((0.1, 0.2, 0.3), 4)
    assert set(canales) == {0, 1, 2, 3}
    assert all(v == (0.1, 0.2, 0.3) for v in canales.values())


def test_fill_siempre_da_al_menos_un_canal():
    assert len(fill((0.0, 0.0, 0.0), 0)) == 1


@pytest.mark.parametrize("nombre", sorted(EFFECTS))
def test_todos_los_modos_devuelven_rgb_valido(nombre):
    efecto = get_effect(nombre)
    for fase in (0.0, 0.25, 0.5, 0.75, 0.99):
        canales = efecto.render(make_ctx(fase))
        assert canales
        for r, g, b in canales.values():
            assert all(0.0 <= c <= 1.0 for c in (r, g, b)), f"{nombre} fuera de rango"


def test_modo_desconocido_da_error_util():
    with pytest.raises(ValueError, match="combo"):
        get_effect("noexiste")


def test_idle_ignora_el_beat():
    """El modo de reposo debe ser estable: si parpadeara, el estado 'no suena
    nada' se confundiria con el de 'suena algo muy flojo'."""
    efecto = get_effect("idle")
    colores = {efecto.render(make_ctx(p))[0] for p in (0.0, 0.3, 0.6, 0.9)}
    assert len(colores) == 1


def test_combo_es_color_espectral_por_brillo_de_beat():
    ctx = make_ctx(0.5)
    combo = get_effect("combo").render(ctx)[0]
    color = spectrum_color(ctx)
    env = beat_envelope(ctx)
    assert combo == pytest.approx(tuple(c * env for c in color))
