"""Sesion completa de Entertainment: CLIP v2 + DTLS + HueStream.

Orden obligatorio, y el orden importa:

  1. `PUT .../entertainment_configuration/<id>` con `action: start`
  2. handshake DTLS contra el puerto 2100
  3. paquetes HueStream por UDP
  4. `action: stop` al salir

Si se salta el paso 1 el bridge ni siquiera contesta al handshake. Si se salta
el 4 el area se queda ocupada y la siguiente sesion falla.
"""

from __future__ import annotations

import contextlib
import time

from .backends import DEFAULT_BACKEND, StreamBackend, StreamError, make_backend
from .rest import BridgeClient, BridgeError

# El bridge cierra la sesion si deja de recibir paquetes ~10 s. Se reenvia el
# ultimo frame bastante antes para no depender de que el llamante mande algo.
KEEPALIVE_INTERVAL = 5.0


class EntertainmentSession:
    def __init__(
        self,
        bridge_ip: str,
        username: str,
        clientkey: str,
        area_id: str,
        reconnect_delay: float = 2.0,
        start_delay: float = 0.6,
        connect_attempts: int = 3,
        backend: str | StreamBackend = DEFAULT_BACKEND,
    ) -> None:
        self.area_id = area_id
        self.bridge_ip = bridge_ip
        self.username = username
        self.clientkey = clientkey
        self.rest = BridgeClient(bridge_ip, username=username)
        self.backend = make_backend(backend) if isinstance(backend, str) else backend
        self.reconnect_delay = reconnect_delay
        self.start_delay = start_delay
        self.connect_attempts = connect_attempts

        self._last_send = 0.0
        self._last_channels: dict[int, tuple[float, float, float]] | None = None
        self._streaming_requested = False
        self._next_reconnect = 0.0
        self.channel_count = 0

    # --- ciclo de vida ------------------------------------------------------

    def start(self) -> None:
        areas = {a.id: a for a in self.rest.get_entertainment_areas()}
        area = areas.get(self.area_id)
        if area is None:
            raise BridgeError(
                f"El area {self.area_id} no existe en el bridge. "
                f"Disponibles: {', '.join(areas) or '(ninguna)'}"
            )
        self.channel_count = area.channel_count

        if area.active:
            # Otra app tiene la sesion abierta (Hue Sync, o una que murio sin
            # mandar stop). Se fuerza el cierre antes de reclamarla.
            self.rest.set_streaming(self.area_id, False)
            time.sleep(0.5)

        self.rest.set_streaming(self.area_id, True)
        self._streaming_requested = True
        self._connect_with_retry()

    def _connect_with_retry(self) -> None:
        """Conecta por DTLS, dandole al bridge tiempo a abrir el listener.

        `action: start` devuelve 200 antes de que el puerto 2100 este realmente
        escuchando, asi que conectar de inmediato hace timeout en el handshake.
        Es una carrera facil de no ver: si el area venia ocupada y hubo que
        cerrarla primero, ese cierre ya introduce la pausa suficiente y todo
        parece funcionar.
        """
        last_error: StreamError | None = None
        for attempt in range(self.connect_attempts):
            time.sleep(self.start_delay if attempt == 0 else self.reconnect_delay)
            try:
                self.backend.connect(
                    self.bridge_ip, self.username, self.clientkey, self.area_id
                )
                return
            except StreamError as exc:
                last_error = exc

        self.rest.set_streaming(self.area_id, False)
        self._streaming_requested = False
        raise last_error if last_error else StreamError("no se pudo conectar")

    def stop(self) -> None:
        self.backend.close()
        if self._streaming_requested:
            # Cerrando: si el bridge ya no responde, insistir no aporta nada y
            # dejaria una excepcion escapando desde un `finally`.
            with contextlib.suppress(BridgeError):
                self.rest.set_streaming(self.area_id, False)
            self._streaming_requested = False

    def __enter__(self) -> EntertainmentSession:
        self.start()
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.stop()

    # --- envio --------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.backend.connected

    def send(self, channels: dict[int, tuple[float, float, float]]) -> bool:
        """Envia un frame. Devuelve False si no se pudo (sin lanzar).

        No lanza a proposito: esto vive en el loop de render a 50 Hz y una
        excepcion por frame perdido tumbaria la app entera. La reconexion se
        maneja aqui dentro.
        """
        if not self.backend.connected:
            self._try_reconnect()
            if not self.backend.connected:
                return False
        try:
            self.backend.send(channels)
        except StreamError:
            return False
        self._last_channels = channels
        self._last_send = time.monotonic()
        return True

    def keepalive(self) -> None:
        """Reenvia el ultimo frame si lleva demasiado sin mandarse."""
        if self._last_channels is None:
            return
        if time.monotonic() - self._last_send >= KEEPALIVE_INTERVAL:
            self.send(self._last_channels)

    def _try_reconnect(self) -> None:
        now = time.monotonic()
        if now < self._next_reconnect:
            return
        self._next_reconnect = now + self.reconnect_delay
        try:
            self.backend.close()
            self.rest.set_streaming(self.area_id, True)
            time.sleep(self.start_delay)
            self.backend.connect(
                self.bridge_ip, self.username, self.clientkey, self.area_id
            )
        except (StreamError, BridgeError):
            pass  # se reintenta en la siguiente ventana
