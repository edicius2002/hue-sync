"""Pruebas del arranque de sync sin audio, bridge ni red."""

from __future__ import annotations

from types import SimpleNamespace

from huebpm.cli import sync
from huebpm.config import Config


def test_roles_invalidos_avisan_antes_del_loop(monkeypatch, capsys):
    """Un dry-run de un canal no puede ocultar que `roles` caera a combo."""
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
    cfg.effects.mode = "roles"
    assert sync.run_sync(cfg, duration=0.1, dry_run=True) == 0
    assert "Aviso: roles no describe todos los canales; se usara combo." in capsys.readouterr().out
