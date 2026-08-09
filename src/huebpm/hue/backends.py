"""Backend de streaming: como se ponen colores en el cable.

Se mantiene la indireccion aunque solo haya una implementacion. No es
especulacion: este proyecto ya cambio de backend una vez, y el seam es lo que
permitio hacerlo sin tocar la sesion, la REST ni el loop de render.

Historia, por si alguien piensa en volver a python-mbedtls: contra un Hue
Bridge BSB002 con firmware 1.78.0 nunca recibe respuesta al ClientHello. El
bridge exige el intercambio de cookie de DTLS (HelloVerifyRequest) y el primer
flight se pierde; python-mbedtls, a traves de su envoltorio de socket, no
retransmite, asi que el handshake muere en silencio. Se probaron los 48
cifrados PSK y DTLS 1.0-1.2 sin diferencia. La implementacion puro-python
reenvia el ClientHello con la cookie y engancha.
"""

from __future__ import annotations

import contextlib
from typing import Protocol, runtime_checkable

Channels = dict[int, tuple[float, float, float]]


class StreamError(RuntimeError):
    """Fallo de conexion o envio hacia el bridge."""


@runtime_checkable
class StreamBackend(Protocol):
    """runtime_checkable para que los dobles de prueba puedan verificar que
    siguen cumpliendo el contrato cuando este cambie."""

    def connect(self, host: str, username: str, clientkey: str, area_id: str) -> None: ...
    def send(self, channels: Channels) -> None: ...
    def close(self) -> None: ...
    @property
    def connected(self) -> bool: ...


class PurePythonBackend:
    """DTLS 1.2 PSK en Python puro sobre `cryptography`, sin bindings C.

    Que no haya extensiones nativas tiene una consecuencia practica: no depende
    de que nadie publique wheels, asi que el proyecto no se queda anclado a una
    version de Python.
    """

    name = "puro-python"

    def __init__(self) -> None:
        self._streamer = None

    def connect(self, host: str, username: str, clientkey: str, area_id: str) -> None:
        try:
            from hue_entertainment.dtls import HueDtlsStreamer
        except ImportError as exc:
            raise StreamError(
                "Falta 'hue-entertainment'.\n"
                "Si lanzaste con el Python del sistema, usa el del entorno:\n"
                "    .\\.venv\\Scripts\\python.exe run.py ...\n"
                "Si no, instala con: pip install hue-entertainment"
            ) from exc

        streamer = HueDtlsStreamer()
        try:
            streamer.connect(host, username, clientkey, area_id)
        except Exception as exc:
            raise StreamError(f"handshake DTLS contra {host}:2100 fallido: {exc}") from exc
        self._streamer = streamer

    def send(self, channels: Channels) -> None:
        if self._streamer is None:
            raise StreamError("backend no conectado")
        from hue_entertainment.dtls import LightColorCommand

        commands = [
            LightColorCommand(
                channel_id=cid,
                red=_to_u16(r),
                green=_to_u16(g),
                blue=_to_u16(b),
            )
            for cid, (r, g, b) in sorted(channels.items())
        ]
        try:
            self._streamer.send_colors(commands)
        except Exception as exc:
            raise StreamError(f"envio fallido: {exc}") from exc

    def close(self) -> None:
        if self._streamer is not None:
            # Cerrando: si el socket ya estaba muerto da igual, y propagar
            # aqui impediria mandar el `action: stop` que viene despues.
            with contextlib.suppress(Exception):
                self._streamer.disconnect()
            self._streamer = None

    @property
    def connected(self) -> bool:
        return self._streamer is not None and bool(self._streamer.is_connected)


BACKENDS = {"pure": PurePythonBackend}
DEFAULT_BACKEND = "pure"


def make_backend(name: str = DEFAULT_BACKEND) -> StreamBackend:
    try:
        return BACKENDS[name]()
    except KeyError:
        raise ValueError(
            f"Backend desconocido {name!r}. Opciones: {', '.join(BACKENDS)}"
        ) from None


def _to_u16(value: float) -> int:
    """Convierte 0.0-1.0 al entero de 16 bits que espera el canal.

    Se cuantiza a 8 bits y se desplaza, en vez de escalar directo a 65535, para
    esquivar un fallo de conversion de `hue-entertainment`:

        r = min(255, cmd.red >> 8) if cmd.red > 255 else cmd.red

    Los valores por encima de 255 se desplazan a 8 bits, pero los de 0 a 255
    pasan tal cual como byte. Eso hace que un 255 de 16 bits, que deberia ser
    un 0.4% de brillo, salga a brillo MAXIMO. Cuantizando primero, ningun valor
    aterriza nunca en ese rango salvo el cero, que si se traduce bien.

    Hoy no nos afecta porque `beat_floor` mantiene los colores por encima del
    umbral, pero bastaria bajarlo a cero para pisar la mina.
    """
    if value <= 0.0:
        return 0
    if value >= 1.0:
        return 0xFFFF
    return int(value * 255) << 8
