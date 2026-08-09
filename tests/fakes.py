"""Dobles de prueba para las rutas que hablan con el bridge.

Ninguno de estos tests toca la red. La gracia de tener la sesion detras de un
`StreamBackend` y de un cliente REST inyectable es justamente esta: se pueden
provocar caidas, timeouts y respuestas raras de forma determinista, cosa que
con un bridge de verdad es imposible.

Viven aqui y no en conftest.py porque conftest es para fixtures; importar
clases de el desde un test es fragil y pytest desaconseja hacerlo.
"""

from __future__ import annotations

from huebpm.hue.backends import StreamError
from huebpm.hue.rest import BridgeError, EntertainmentArea


class FakeBackend:
    """Backend de streaming controlable: se le puede pedir que falle."""

    name = "fake"

    def __init__(self, fail_connect: int = 0, fail_send: bool = False) -> None:
        self.fail_connect = fail_connect  # cuantas conexiones fallan al inicio
        self.fail_send = fail_send
        self._connected = False

        self.connects = 0
        self.closes = 0
        self.sent: list[dict] = []

    def connect(self, host: str, username: str, clientkey: str, area_id: str) -> None:
        self.connects += 1
        if self.fail_connect > 0:
            self.fail_connect -= 1
            raise StreamError("fallo simulado de handshake")
        self._connected = True

    def send(self, channels) -> None:  # noqa: ANN001
        if self.fail_send or not self._connected:
            raise StreamError("fallo simulado de envio")
        self.sent.append(dict(channels))

    def close(self) -> None:
        self.closes += 1
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def drop(self) -> None:
        """Simula que se cae la conexion sin avisar."""
        self._connected = False


class FakeRest:
    """Cliente REST falso que registra las llamadas y puede fallar."""

    def __init__(self, areas=None, fail_stop: bool = False) -> None:
        self.areas = areas if areas is not None else [
            EntertainmentArea(id="area-1", name="salon", channel_count=3, status="inactive")
        ]
        self.fail_stop = fail_stop
        self.actions: list[tuple[str, bool]] = []
        self.username = "u" * 40

    def get_entertainment_areas(self):
        return list(self.areas)

    def set_streaming(self, area_id: str, active: bool) -> None:
        if not active and self.fail_stop:
            raise BridgeError("fallo simulado al parar")
        self.actions.append((area_id, active))
