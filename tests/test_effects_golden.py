"""Red de seguridad: congela el render de los siete looks.

Sin este fichero, "lo que ya funciona sigue igual" es una promesa; con el es
verificable, porque cualquier retoque en `beat_envelope`, `spectrum_color` o el
orden de las operaciones de color rompe un numero exacto.

Cubre dos propiedades distintas, y por eso hay dos listas:

* `MODOS_CONGELADOS` (siete) responde "ningun look cambia de render por
  accidente". Es la tabla de valores.
* `MODOS_ORIGINALES` (seis) responde "ningun modo anterior a `sustain` lee esa
  senal". No depende de la tabla: compara los extremos 0.0 y 1.0, asi que
  sigue detectando la regresion aunque alguien regenere los valores.

El mismo control por extremos cubre ahora `sub_bass`, `beat_strength` y
`onset_rate`, declarados por el contrato de la capa de composicion y que
todavia nadie puebla.

Se listan a mano y NO se recorre `EFFECTS`: un look nuevo tiene que entrar aqui
por decision explicita, no por aparecer en el registro.

Este fichero lo mantiene main. Los workers no lo editan: debilitarlo —subir
tolerancias, sacar looks de la tabla— vaciaria de sentido el control. Un cambio
de comportamiento intencionado regenera los valores en un commit APARTE que
diga por que y con que se midio; si la tabla cambia sin esa justificacion, la
entrega se rechaza por proceso aunque el codigo este bien.
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

MODOS_CONGELADOS = (*MODOS_ORIGINALES, "sustain")
"""Los SIETE looks. `sustain` entra ahora que esta calibrado y estable.

Se congela por separado de la lista de arriba porque cumple otro papel:
`MODOS_ORIGINALES` responde "ningun modo viejo lee la senal nueva" y esta
responde "el render de ningun look cambia por accidente".

`roles` no esta: no es un look, es el compositor, y su render se define por el
de los looks que compone.
"""

CAMPOS_NUEVOS = ("sub_bass", "beat_strength", "onset_rate")
"""Los tres campos que declara el contrato y que todavia nadie puebla."""


def contexto(fase: float, sustain: float = 1.0, **campos_nuevos: float) -> RenderContext:
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
            **campos_nuevos,
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
    "sustain": {
        0.0: (0.783923076923, 0.339846153846, 0.093923076923),
        0.25: (0.690349152401, 0.299280007390, 0.082711835451),
        0.5: (0.596775227879, 0.258713860933, 0.071500593979),
        0.75: (0.690349152401, 0.299280007390, 0.082711835451),
        0.99: (0.783738430158, 0.339766105823, 0.093900954099),
    },
}


@pytest.mark.parametrize("nombre", MODOS_CONGELADOS)
def test_el_render_de_los_looks_no_cambia(nombre):
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


@pytest.mark.parametrize("nombre", MODOS_CONGELADOS)
@pytest.mark.parametrize("campo", CAMPOS_NUEVOS)
def test_ningun_look_lee_los_campos_nuevos(nombre, campo):
    """La propiedad de seguridad del contrato.

    `sub_bass`, `beat_strength` y `onset_rate` estan declarados pero nadie los
    puebla todavia. Hasta que alguien lo haga, ningun look puede mirarlos: si
    uno empieza a reaccionar antes de que la senal exista, veria siempre 0.0 y
    el sintoma seria "este modo no hace nada", que es de los mas caros de
    diagnosticar.

    Comparar los extremos 0.0 y 1.0 lo detecta sin depender de la tabla
    congelada, igual que el control de `sustain`.
    """
    efecto = get_effect(nombre)
    for fase in FASES:
        apagado = efecto.render(contexto(fase, **{campo: 0.0}))[0]
        encendido = efecto.render(contexto(fase, **{campo: 1.0}))[0]
        assert apagado == pytest.approx(encendido, abs=1e-12), (
            f"{nombre} reacciona a {campo} y todavia no deberia"
        )


@pytest.mark.parametrize("campo", CAMPOS_NUEVOS)
def test_los_campos_nuevos_arrancan_apagados(campo):
    """Mismo argumento que con `sustain`: cablear el detector mas adelante no
    puede encender nada por sorpresa."""
    assert getattr(AudioState(), campo) == 0.0


def test_la_capa_de_composicion_esta_declarada_pero_inerte():
    """El contrato declara la config; la implementacion viene despues.

    Este test es el que hace verificable que T0 no cambio comportamiento: los
    campos existen con sus defaults y `fill()` sigue clonando el mismo color a
    todos los canales, sin mirar `channel_modes` ni `channel_gain`.
    """
    cfg = EffectsConfig()
    assert cfg.channel_modes == ("combo", "harmony")
    assert cfg.channel_gain == (0.7, 1.0)
    assert cfg.ceiling_channel is None
    assert cfg.ceiling_max_step == 0.03
    assert cfg.ceiling_clamp is True

    ctx = RenderContext(
        now=ANCHOR,
        state=AudioState(bands=np.array(BANDAS), locked=True),
        clock=BeatClock(),
        channel_count=2,
        cfg=cfg,
    )
    canales = get_effect("combo").render(ctx)
    assert canales[0] == canales[1], "combo dejo de clonar antes de que exista la capa"
