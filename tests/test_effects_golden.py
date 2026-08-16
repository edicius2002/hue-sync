"""Red de seguridad: congela el render de los seis modos originales.

Existe por una razon concreta. Se esta anadiendo un modo sostenido que cambia
el brillo de destello a continuo, y el requisito es que **el modo BPM original
siga funcionando sin cambios**. Sin este fichero eso es una promesa; con el es
verificable: cualquier retoque en `beat_envelope`, `spectrum_color` o el orden
de las operaciones de color rompe un numero exacto.

Los valores se generaron con `sustain=1.0`, o sea con la senal nueva al maximo.
Que coincidan con el comportamiento historico es justo lo que se quiere
demostrar: los modos originales **no leen** el campo nuevo.

Este fichero lo mantiene main. Los workers no lo editan: debilitarlo (subir
tolerancias, quitar modos de la tabla) vaciaria de sentido el control. Si un
cambio de comportamiento es intencionado, se regeneran los valores en un commit
aparte que diga por que.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.beatclock import BeatClock
from huebpm.analysis.tempo import TempoEstimate
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext
from huebpm.effects.modes import get_effect
from huebpm.state import AudioState

PERIOD = 0.5
ANCHOR = 100.0
BANDAS = (0.9, 0.3, 0.1)
TONALIDAD = 0.5
FASES = (0.0, 0.25, 0.5, 0.75, 0.99)

MODOS_ORIGINALES = ("combo", "harmony", "bars", "beat_flash", "spectrum", "idle")
"""Los seis de antes del modo sostenido.

Se listan a mano y NO se recorre `EFFECTS` a proposito: cuando se registre el
modo nuevo, ese si tiene que responder a `sustain`, asi que recorrer el registro
lo metería aqui y el control empezaria a fallar por la razon equivocada.
"""


def contexto(fase: float, sustain: float = 1.0) -> RenderContext:
    clock = BeatClock()
    clock.update(
        TempoEstimate(bpm=120.0, period=PERIOD, last_beat_time=ANCHOR, confidence=1.0),
        ANCHOR,
    )
    return RenderContext(
        now=ANCHOR + fase * PERIOD,
        state=AudioState(
            bands=np.array(BANDAS),
            locked=True,
            tonality=TONALIDAD,
            sustain=sustain,
        ),
        clock=clock,
        channel_count=1,
        cfg=EffectsConfig(),
    )


GOLDEN: dict[str, dict[float, tuple[float, float, float]]] = {
    "combo": {
        0.0: (0.783923076923, 0.339846153846, 0.093923076923),
        0.25: (0.347853250675, 0.150801262043, 0.041676853996),
        0.5: (0.187432126684, 0.081255532891, 0.022456542702),
        0.75: (0.128416493238, 0.055671088914, 0.015385785325),
        0.99: (0.699866554386, 0.303405989332, 0.083852130596),
    },
    "harmony": {
        0.0: (1.0, 0.0, 0.0),
        0.25: (1.0, 0.0, 0.0),
        0.5: (1.0, 0.0, 0.0),
        0.75: (1.0, 0.0, 0.0),
        0.99: (1.0, 0.0, 0.0),
    },
    "bars": {
        0.0: (0.783923076923, 0.339846153846, 0.093923076923),
        0.25: (0.347853250675, 0.150801262043, 0.041676853996),
        0.5: (0.187432126684, 0.081255532891, 0.022456542702),
        0.75: (0.128416493238, 0.055671088914, 0.015385785325),
        0.99: (0.699866554386, 0.303405989332, 0.083852130596),
    },
    "beat_flash": {
        0.0: (1.0, 0.55, 0.2),
        0.25: (0.443733908231, 0.244053649527, 0.088746781646),
        0.5: (0.239095049248, 0.131502277087, 0.047819009850),
        0.75: (0.163812620164, 0.090096941090, 0.032762524033),
        0.99: (0.892774527232, 0.491025989978, 0.178554905446),
    },
    "spectrum": {
        0.0: (0.714937846154, 0.309939692308, 0.085657846154),
        0.25: (0.714937846154, 0.309939692308, 0.085657846154),
        0.5: (0.714937846154, 0.309939692308, 0.085657846154),
        0.75: (0.714937846154, 0.309939692308, 0.085657846154),
        0.99: (0.714937846154, 0.309939692308, 0.085657846154),
    },
    "idle": {
        0.0: (0.07, 0.0385, 0.014),
        0.25: (0.07, 0.0385, 0.014),
        0.5: (0.07, 0.0385, 0.014),
        0.75: (0.07, 0.0385, 0.014),
        0.99: (0.07, 0.0385, 0.014),
    },
}


@pytest.mark.parametrize("nombre", MODOS_ORIGINALES)
def test_el_render_de_los_modos_originales_no_cambia(nombre):
    efecto = get_effect(nombre)
    for fase in FASES:
        obtenido = efecto.render(contexto(fase))[0]
        assert obtenido == pytest.approx(GOLDEN[nombre][fase], abs=1e-9), (
            f"{nombre} cambio en fase {fase}"
        )


@pytest.mark.parametrize("nombre", MODOS_ORIGINALES)
def test_los_modos_originales_ignoran_el_sustain(nombre):
    """Lo que de verdad protege esto.

    El campo `sustain` es nuevo y ningun modo de antes debe mirarlo. Comparar
    los extremos 0.0 y 1.0 lo demuestra sin depender de los valores congelados:
    aunque alguien regenere la tabla de arriba, esta comparacion sigue
    detectando que un modo viejo empezo a reaccionar a la senal nueva.
    """
    efecto = get_effect(nombre)
    for fase in FASES:
        apagado = efecto.render(contexto(fase, sustain=0.0))[0]
        encendido = efecto.render(contexto(fase, sustain=1.0))[0]
        assert apagado == pytest.approx(encendido, abs=1e-12), (
            f"{nombre} reacciona a sustain y no deberia"
        )


def test_el_campo_sustain_arranca_apagado():
    """Con el default a cero, cablear el detector mas adelante no puede
    encender nada por sorpresa: hasta que alguien lo pueble, el estado publica
    exactamente lo de siempre."""
    assert AudioState().sustain == 0.0
