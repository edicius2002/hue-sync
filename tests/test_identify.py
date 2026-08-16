"""Pruebas del identificador de canales Entertainment sin bridge real."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from huebpm.cli import identify


class FakeSession:
    """Sesion que guarda frames para comprobar que una sola luz se enciende."""

    def __init__(self, channels: int, fail_send: bool = False) -> None:
        self.channel_count = channels
        self.fail_send = fail_send
        self.started = False
        self.stopped = False
        self.frames: list[dict[int, tuple[float, float, float]]] = []

    def start(self) -> None:
        self.started = True

    def send(self, channels: dict[int, tuple[float, float, float]]) -> bool:
        if self.fail_send:
            raise RuntimeError("fallo simulado de envio")
        self.frames.append(channels)
        return True

    def stop(self) -> None:
        self.stopped = True


def preparar(monkeypatch, channels: int, fail_send: bool = False) -> FakeSession:
    session = FakeSession(channels, fail_send)
    reloj = [0.0]

    class Limiter:
        def __init__(self, fps: float) -> None:
            self.fps = fps

        def tick(self) -> float:
            reloj[0] += 1.0 / self.fps
            return reloj[0]

    class Timer:
        def __init__(self, resolution: int) -> None:
            self.resolution = resolution

        def __enter__(self) -> Timer:
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

    monkeypatch.setattr(identify, "EntertainmentSession", lambda *args, **kwargs: session)
    monkeypatch.setattr(identify, "load_hue_credentials", lambda: SimpleNamespace(
        bridge_ip="1.2.3.4", username="u", clientkey="k", entertainment_area_id="area"
    ))
    monkeypatch.setattr(identify, "RateLimiter", Limiter)
    monkeypatch.setattr(identify, "TimerResolution", Timer)
    monkeypatch.setattr(identify.time, "perf_counter", lambda: reloj[0])
    return session


def config():
    return SimpleNamespace(render=SimpleNamespace(fps=10.0))


def canales_encendidos(session: FakeSession) -> list[int]:
    activos = []
    for frame in session.frames:
        encendidos = [canal for canal, color in frame.items() if color != identify.APAGADO]
        assert len(encendidos) == 1
        activos.append(encendidos[0])
    return activos


def test_enciende_un_solo_canal_y_los_recorre_en_orden(monkeypatch):
    session = preparar(monkeypatch, channels=2)

    assert identify.run_identify(config(), seconds=0.2, rounds=2) == 0

    activos = canales_encendidos(session)
    cambios = [canal for i, canal in enumerate(activos) if i == 0 or canal != activos[i - 1]]
    assert cambios == [0, 1, 0, 1]
    assert session.started
    assert session.stopped


def test_asigna_colores_distintos_a_canales_distintos(monkeypatch):
    session = preparar(monkeypatch, channels=2)

    identify.run_identify(config(), seconds=0.2, rounds=1)

    activos = canales_encendidos(session)
    colores = [frame[canal] for frame, canal in zip(session.frames, activos, strict=True)]
    assert colores[0] != colores[-1]


def test_funciona_con_un_solo_canal(monkeypatch):
    session = preparar(monkeypatch, channels=1)

    assert identify.run_identify(config(), seconds=0.2, rounds=1) == 0
    assert canales_encendidos(session) == [0, 0]


def test_cierra_la_sesion_si_falla_el_envio(monkeypatch):
    session = preparar(monkeypatch, channels=2, fail_send=True)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        identify.run_identify(config(), seconds=0.2, rounds=1)

    assert session.stopped
