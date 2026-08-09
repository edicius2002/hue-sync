"""Tests del chroma y del modo `harmony`.

El ground truth aqui es exacto: se sintetizan acordes de notas conocidas y se
comprueba que el detector las encuentra. Las notas llevan armonicos a
proposito — un detector que solo funcione con senos puros no serviria para
instrumentos reales, porque el tercer armonico cae una quinta arriba, o sea en
otra clase de altura.
"""

from __future__ import annotations

import numpy as np
import pytest

from huebpm.analysis.chroma import N_PITCH_CLASSES, ChromaAnalyzer
from huebpm.config import EffectsConfig
from huebpm.effects.base import RenderContext, harmony_color, harmony_mix
from huebpm.effects.modes import get_effect
from huebpm.state import AudioState
from huebpm.testing.synth import chord, note_hz, progression, tone

SR = 48000


def analizar(audio: np.ndarray, **kwargs) -> ChromaAnalyzer:
    ca = ChromaAnalyzer(SR, **kwargs)
    ca.process(audio)
    return ca


# --- resolucion --------------------------------------------------------------


def test_el_fft_resuelve_semitonos_en_el_registro_util():
    """Justifica por que el chroma NO reutiliza el FFT de la ODF: con 1024
    muestras los semitonos solo se separan por encima de 788 Hz."""
    for fft_size, esperado_max in ((1024, 800.0), (8192, 100.0)):
        ancho = SR / fft_size
        primera_resoluble = ancho / (2 ** (1 / 12) - 1)
        assert primera_resoluble <= esperado_max


@pytest.mark.parametrize("pc", range(N_PITCH_CLASSES))
def test_identifica_cada_nota_suelta(pc):
    ca = analizar(tone(note_hz(pc, 3), 1.5, SR))
    assert ca.dominant == pc, f"esperaba {pc}, dio {ca.dominant}"


@pytest.mark.parametrize("root,calidad", [
    (0, "maj"), (7, "maj"), (9, "min"), (5, "maj7"), (2, "power"), (11, "min"),
])
def test_encuentra_todas_las_notas_del_acorde(root, calidad):
    audio, esperadas = chord(root, calidad, 2.0, SR)
    ca = analizar(audio)
    mejores = set(np.argsort(ca.chroma)[::-1][: len(esperadas)])
    assert mejores == set(esperadas)


# --- tonalidad ---------------------------------------------------------------


def test_el_ruido_no_tiene_tonalidad():
    rng = np.random.default_rng(0)
    ca = analizar((rng.standard_normal(SR * 2) * 0.3).astype(np.float32))
    assert ca.tonality < 0.05


def test_un_acorde_si_tiene_tonalidad():
    ca = analizar(chord(0, "maj", 2.0, SR)[0])
    assert ca.tonality > 0.15


def test_la_tonalidad_separa_musica_de_ruido():
    """Regresion: la primera version media la magnitud de la media vectorial y
    daba 0.14 para un Do mayor contra 0.13 para ruido blanco, o sea que no
    separaba nada. Las notas de una triada estan a 120 y 90 grados y sus
    vectores casi se cancelan."""
    rng = np.random.default_rng(1)
    ruido = analizar((rng.standard_normal(SR * 2) * 0.3).astype(np.float32)).tonality
    acorde = analizar(chord(0, "maj", 2.0, SR)[0]).tonality
    assert acorde > 10 * ruido


def test_una_nota_sola_es_mas_tonal_que_un_acorde():
    sola = analizar(tone(note_hz(0, 3), 2.0, SR)).tonality
    triada = analizar(chord(0, "maj", 2.0, SR)[0]).tonality
    assert sola > triada


def test_silencio_no_revienta():
    ca = analizar(np.zeros(SR, dtype=np.float32))
    assert ca.tonality == 0.0
    assert ca.hue == 0.0


# --- estabilidad y cambio ----------------------------------------------------


def test_el_color_es_estable_mientras_dura_el_acorde():
    """El punto entero del modo: con bandas el color parpadea con cada golpe,
    con armonia se queda quieto mientras no cambie el acorde."""
    audio, _ = chord(0, "maj", 3.0, SR)
    ca = ChromaAnalyzer(SR)
    bloque = 2048
    hues = []
    for s in range(0, len(audio) - bloque, bloque):
        if ca.process(audio[s : s + bloque]) is not None:
            hues.append(ca.hue)
    estables = hues[len(hues) // 3 :]  # tras converger el suavizado
    assert max(estables) - min(estables) < 0.12


def test_acordes_distintos_dan_colores_distintos():
    hues = [analizar(chord(root, "maj", 2.0, SR)[0]).hue for root in (0, 5, 7)]
    for a, b in ((0, 1), (1, 2), (0, 2)):
        distancia = abs(hues[a] - hues[b])
        distancia = min(distancia, 1.0 - distancia)  # circular
        assert distancia > 0.08, f"{hues[a]:.3f} y {hues[b]:.3f} son casi iguales"


def test_volver_al_mismo_acorde_devuelve_el_mismo_color():
    """C - F - G - C: el ultimo tiene que parecerse al primero."""
    audio, _ = progression([0, 5, 7, 0], bar_seconds=2.0, samplerate=SR)
    ca = ChromaAnalyzer(SR)
    bloque = 2048
    hues = []
    for s in range(0, len(audio) - bloque, bloque):
        if ca.process(audio[s : s + bloque]) is not None:
            hues.append((s / SR, ca.hue))

    def medio(desde, hasta):
        tramo = [h for t, h in hues if desde <= t <= hasta]
        return sum(tramo) / len(tramo)

    primero, ultimo = medio(0.8, 1.8), medio(6.8, 7.8)
    distancia = abs(primero - ultimo)
    assert min(distancia, 1.0 - distancia) < 0.06


# --- efecto ------------------------------------------------------------------


def contexto(tonality: float, hue: float = 0.3, cfg=None):
    return RenderContext(
        now=0.0,
        state=AudioState(
            bands=np.array([0.5, 0.5, 0.5]), chroma_hue=hue, tonality=tonality
        ),
        clock=__import__("huebpm.analysis.beatclock", fromlist=["BeatClock"]).BeatClock(),
        channel_count=1,
        cfg=cfg or EffectsConfig(),
    )


def test_sin_tonalidad_no_se_usa_la_armonia():
    assert harmony_mix(contexto(tonality=0.0)) == 0.0


def test_con_tonalidad_alta_el_color_es_armonia_pura():
    assert harmony_mix(contexto(tonality=0.5)) == 1.0


def test_la_mezcla_es_progresiva_no_un_escalon():
    """Regresion: con un umbral duro, cruzarlo daba un salto de color de casi
    todo el rango RGB, visible como un fogonazo."""
    cfg = EffectsConfig()
    medio = (cfg.harmony_min_tonality + cfg.harmony_full_tonality) / 2
    mix = harmony_mix(contexto(tonality=medio))
    assert 0.3 < mix < 0.7


def test_mas_tonalidad_da_mas_saturacion():
    def saturacion(t):
        r, g, b = harmony_color(contexto(tonality=t))
        return max(r, g, b) - min(r, g, b)

    assert saturacion(0.02) < saturacion(0.08)


def test_el_modo_harmony_cae_a_espectral_sin_armonia():
    """Inventarse un tono con percusion sola daria un color aleatorio que salta
    en cada golpe: peor que no seguir la armonia."""
    efecto = get_effect("harmony")
    color = efecto.render(contexto(tonality=0.0))[0]
    assert all(0.0 <= c <= 1.0 for c in color)


def test_el_modo_harmony_devuelve_rgb_valido():
    efecto = get_effect("harmony")
    for t in (0.0, 0.1, 0.5, 1.0):
        for h in (0.0, 0.25, 0.5, 0.99):
            for c in efecto.render(contexto(tonality=t, hue=h))[0]:
                assert 0.0 <= c <= 1.0


def test_harmony_pulsa_menos_que_los_demas_modos():
    """La razon de ser del modo: si la luz parpadea igual de fuerte que en
    `combo`, el pulso domina la percepcion y el color no se ve. Medido en la
    practica, los dos modos parecian identicos."""
    ctx = contexto(tonality=0.5)
    combo = get_effect("combo").render(ctx)[0]
    harmony = get_effect("harmony").render(ctx)[0]
    assert max(harmony) > max(combo), "harmony debe mantener mas brillo entre golpes"


def test_la_conversion_a_16_bits_esquiva_la_rama_rota_de_la_libreria():
    """`hue-entertainment` trata los valores de 0 a 255 como byte directo en vez
    de desplazarlos, asi que un 0.4% de brillo saldria a brillo maximo."""
    from huebpm.hue.backends import _to_u16

    for v in (0.0005, 0.001, 0.002, 0.003, 0.0039):
        u = _to_u16(v)
        assert u == 0 or u > 255, f"{v} -> {u} cae en la zona rota"


def test_la_envolvente_de_harmony_es_fluida():
    """Regresion: con la envolvente de pico, el brillo saltaba 0.150 por frame
    de render y se percibia como parpadeo pese a tener poco rango. La forma
    importa mas que la profundidad."""
    import numpy as np

    from huebpm.analysis.tempo import TempoEstimate
    from huebpm.effects.modes import get_effect

    ctx = contexto(tonality=0.5)
    ctx.clock.update(
        TempoEstimate(bpm=120.0, period=0.5, last_beat_time=0.0, confidence=1.0), 0.0
    )
    efecto = get_effect("harmony")
    paso = 1.0 / 50.0  # un frame de render
    brillos = []
    for i in range(int(0.5 / paso) + 1):
        c = RenderContext(
            now=i * paso, state=ctx.state, clock=ctx.clock,
            channel_count=1, cfg=ctx.cfg,
        )
        brillos.append(max(efecto.render(c)[0]))
    saltos = np.abs(np.diff(brillos))
    assert saltos.max() < 0.035, f"salta {saltos.max():.3f} por frame, parpadea"


@pytest.mark.parametrize("bpm", [76.0, 120.0, 174.0])
def test_el_brillo_de_harmony_es_constante_por_defecto(bpm):
    """Cualquier bajada entre cambios de color se percibe como un apagado, no
    como parte de la musica."""
    from huebpm.analysis.tempo import TempoEstimate
    from huebpm.effects.modes import get_effect

    ctx = contexto(tonality=0.5)
    ctx.clock.update(
        TempoEstimate(bpm=bpm, period=60 / bpm, last_beat_time=0.0, confidence=1.0), 0.0
    )
    efecto = get_effect("harmony")
    brillos = {
        round(max(efecto.render(RenderContext(
            now=i / 50.0, state=ctx.state, clock=ctx.clock,
            channel_count=1, cfg=ctx.cfg, render_fps=50.0,
        ))[0]), 6)
        for i in range(int(50 * 60 / bpm) + 1)
    }
    assert len(brillos) == 1


@pytest.mark.parametrize("bpm", [76.0, 120.0, 174.0])
def test_la_pendiente_se_acota_igual_a_cualquier_tempo(bpm):
    """La fase avanza (BPM/60)/fps por frame, asi que una profundidad comoda a
    120 BPM parpadearia a 174. Se recorta la profundidad, no el resultado."""
    import numpy as np

    from huebpm.analysis.tempo import TempoEstimate
    from huebpm.effects.modes import get_effect

    cfg = EffectsConfig()
    cfg.harmony_beat_depth = 0.9  # exagerado a proposito
    ctx = contexto(tonality=0.5, cfg=cfg)
    ctx.clock.update(
        TempoEstimate(bpm=bpm, period=60 / bpm, last_beat_time=0.0, confidence=1.0), 0.0
    )
    efecto = get_effect("harmony")
    brillos = [
        max(efecto.render(RenderContext(
            now=i / 50.0, state=ctx.state, clock=ctx.clock,
            channel_count=1, cfg=cfg, render_fps=50.0,
        ))[0])
        for i in range(int(50 * 60 / bpm) + 1)
    ]
    saltos = np.abs(np.diff(brillos))
    assert saltos.max() <= cfg.harmony_max_step + 0.002
