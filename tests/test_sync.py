"""Pruebas del arranque de sync sin audio, bridge ni red."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from huebpm.cli import sync
from huebpm.config import Config
from huebpm.state import AudioState


def ejecutar_frames(monkeypatch, estados, instantes, *, mode=None, cfg=None):
    """Corre frames reales de sync con dobles que solo reemplazan I/O."""
    enviados: list[dict[int, tuple[float, float, float]]] = []

    class Capture:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class Analyzer:
        def __init__(self, *args) -> None:  # noqa: ANN002
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class Engine:
        def __init__(self) -> None:
            self.clock = SimpleNamespace(locked=False, beat_index=lambda now: None)
            self.bars = SimpleNamespace(locked=False)
            self._estados = iter(estados)

        @property
        def state(self):
            return next(self._estados)

    class Limiter:
        def __init__(self, fps: float) -> None:
            self.jitter = SimpleNamespace(mean_ms=0.0, max_ms=0.0)
            self._instantes = iter(instantes)

        def tick(self) -> float:
            return next(self._instantes)

    class Timer:
        def __init__(self, resolution: int) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

    class Session:
        def __init__(self, *args) -> None:  # noqa: ANN002
            self.channel_count = 2

        def start(self) -> None:
            pass

        def send(self, channels) -> bool:  # noqa: ANN001
            enviados.append(channels)
            return True

        def keepalive(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(
        sync,
        "resolve_device",
        lambda *args: SimpleNamespace(index=0, name="falso", samplerate=48000.0),
    )
    monkeypatch.setattr(sync, "LoopbackCapture", Capture)
    monkeypatch.setattr(sync, "AnalysisEngine", lambda *args: Engine())
    monkeypatch.setattr(sync, "LiveAnalyzer", Analyzer)
    monkeypatch.setattr(sync, "RateLimiter", Limiter)
    monkeypatch.setattr(sync, "TimerResolution", Timer)
    monkeypatch.setattr(sync, "EntertainmentSession", Session)
    monkeypatch.setattr(
        sync,
        "load_hue_credentials",
        lambda: SimpleNamespace(
            bridge_ip="127.0.0.1", username="usuario", clientkey="clave", entertainment_area_id="area"
        ),
    )
    monkeypatch.setattr(sync, "_status", lambda *args: None)
    monkeypatch.setattr(sync.time, "perf_counter", lambda: instantes[0])

    cfg = cfg or Config()
    cfg.effects.ceiling_channel = 1
    assert sync.run_sync(cfg, duration=0.1, mode=mode) == 0
    return enviados


def test_composicion_invalida_avisa_antes_del_loop(monkeypatch, capsys):
    """Un dry-run de un canal no puede ocultar el fallback de toda el area."""
    reloj = [0.0]

    class Capture:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class Analyzer:
        def __init__(self, *args) -> None:  # noqa: ANN002
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class Limiter:
        def __init__(self, fps: float) -> None:
            self.jitter = SimpleNamespace(mean_ms=0.0, max_ms=0.0)

        def tick(self) -> float:
            return 1.0

    class Timer:
        def __init__(self, resolution: int) -> None:
            pass

        def __enter__(self) -> Timer:
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

    monkeypatch.setattr(
        sync,
        "resolve_device",
        lambda *args: SimpleNamespace(index=0, name="falso", samplerate=48000.0),
    )
    monkeypatch.setattr(sync, "LoopbackCapture", Capture)
    monkeypatch.setattr(sync, "AnalysisEngine", lambda *args: object())
    monkeypatch.setattr(sync, "LiveAnalyzer", Analyzer)
    monkeypatch.setattr(sync, "RateLimiter", Limiter)
    monkeypatch.setattr(sync, "TimerResolution", Timer)
    monkeypatch.setattr(sync.time, "perf_counter", lambda: reloj[0])

    cfg = Config()
    assert sync.run_sync(cfg, duration=0.1, dry_run=True) == 0
    salida = capsys.readouterr().out
    assert "AVISO: composicion invalida" in salida
    assert "esperaba 1" in salida
    assert "channel_modes=('combo', 'harmony')" in salida


def test_el_guard_cenital_conserva_idle_al_volver_el_audio(monkeypatch):
    """El primer frame tras silencio parte del idle fisico, no de la nada.

    Conservar el ultimo RGB, ya transformado por la salida, deja el primer
    salto en 0.03. Limpiar la memoria deja sin cota el retorno del audio.
    """
    estados = (
        AudioState(silent=True, bands=np.array((0.9, 0.3, 0.1))),
        AudioState(silent=False, bands=np.array((0.9, 0.3, 0.1)), tonality=0.5),
    )
    enviados = ejecutar_frames(monkeypatch, estados, (100.0, 100.02, 101.0))

    assert len(enviados) == 2
    brillo_idle = max(enviados[0][1])
    brillo_retorno = max(enviados[1][1])
    assert brillo_retorno - brillo_idle <= 0.03 + 1e-12


def test_composicion_invalida_con_controles_validos_alcanza_el_loop(monkeypatch):
    """El aviso de una lista corta no puede indexar el canal cenital ausente."""
    cfg = Config()
    cfg.effects.channel_modes = ("combo",)
    estados = (AudioState(silent=False, bands=np.array((0.9, 0.3, 0.1))),)

    enviados = ejecutar_frames(monkeypatch, estados, (100.0, 101.0), cfg=cfg)

    assert len(enviados) == 1
    assert set(enviados[0]) == {0, 1}


def test_idle_conserva_su_brillo_configurado_antes_del_recorte(monkeypatch):
    """Rango y normalizacion solo dan forma a musica; idle sigue siendo tenue."""
    estados = (AudioState(silent=True, bands=np.array((0.9, 0.3, 0.1))),)

    enviados = ejecutar_frames(monkeypatch, estados, (100.0, 101.0))

    assert max(enviados[0][0]) == 0.07
    assert max(enviados[0][1]) == 0.07


def test_mode_explicitamente_sobre_escribe_la_composicion_en_el_loop(monkeypatch):
    """`--mode spectrum` conserva el look aunque cada canal tenga su salida."""
    estados = (AudioState(silent=False, bands=np.array((0.9, 0.3, 0.1))),)
    enviados = ejecutar_frames(monkeypatch, estados, (100.0, 101.0), mode="spectrum")

    assert len(enviados) == 1
    assert max(enviados[0][0]) > 0.7
    assert max(enviados[0][1]) > 0.9
