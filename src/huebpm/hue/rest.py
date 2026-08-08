"""Cliente REST del bridge (CLIP v2).

Solo para setup y lectura de configuracion: registro de credenciales, listado
de entertainment areas y arranque/parada de la sesion de streaming. El loop
principal NO pasa por aqui — la REST API va a ~1 Hz y para sincronizar con la
musica hace falta el canal DTLS.
"""

from __future__ import annotations

import socket
import warnings
from dataclasses import dataclass
from typing import Any

import requests
import urllib3


class LinkButtonNotPressed(RuntimeError):
    """El bridge exige pulsar su boton fisico antes de emitir credenciales."""


class BridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntertainmentArea:
    id: str
    name: str
    channel_count: int
    status: str

    @property
    def active(self) -> bool:
        return self.status == "active"


class BridgeClient:
    """
    Sobre la verificacion TLS: el bridge presenta un certificado autofirmado
    cuyo CN es su bridge id, asi que la verificacion estandar siempre falla.
    Verificar de verdad exigiria pinning del certificado. Se desactiva a
    proposito y se limita el riesgo a que el destino es una IP de la red local
    que el usuario configura explicitamente. No pongas esto contra un host
    remoto.
    """

    def __init__(self, ip: str, username: str | None = None, timeout: float = 5.0) -> None:
        self.ip = ip
        self.username = username
        self.timeout = timeout
        self._session = requests.Session()
        self._session.verify = False

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if self.username:
            headers["hue-application-key"] = self.username
        url = f"https://{self.ip}{path}"
        # Se silencia solo esta advertencia, y solo aqui, en vez de apagarla
        # globalmente para todo el proceso.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            try:
                response = self._session.request(
                    method, url, headers=headers, timeout=self.timeout, **kwargs
                )
            except requests.exceptions.ConnectTimeout as exc:
                raise BridgeError(
                    f"El bridge en {self.ip} no responde (timeout). Comprueba la "
                    "IP y que estas en la misma red."
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                # El volcado de requests aqui es una pared de texto inutil para
                # el usuario; el diagnostico real casi siempre es la IP.
                raise BridgeError(
                    f"No se pudo conectar a {self.ip}:443. Comprueba que esa es "
                    "la IP del bridge (la ves en la app movil de Hue, en "
                    "Configuracion > Puentes) y que estas en la misma red."
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise BridgeError(f"Error hablando con el bridge: {exc}") from exc

        if response.status_code == 401:
            raise BridgeError(
                "Credenciales rechazadas por el bridge. Vuelve a registrar."
            )
        if not response.ok:
            raise BridgeError(f"HTTP {response.status_code} en {path}: {response.text[:200]}")
        return response.json()

    # --- Registro (API v1: es la unica que emite credenciales) ---------------

    @staticmethod
    def default_devicetype() -> str:
        # El bridge limita devicetype a 40 caracteres con formato app#dispositivo.
        host = socket.gethostname()[:20]
        return f"hue_bpm_sync#{host}"

    def create_user(self, devicetype: str | None = None) -> tuple[str, str]:
        """Pide credenciales nuevas. Requiere el boton del bridge pulsado.

        Devuelve (username, clientkey). El clientkey es la PSK del handshake
        DTLS y solo se emite si se pide `generateclientkey`; sin el no hay
        Entertainment API.
        """
        payload = {
            "devicetype": devicetype or self.default_devicetype(),
            "generateclientkey": True,
        }
        data = self._request("POST", "/api", json=payload)

        if not isinstance(data, list) or not data:
            raise BridgeError(f"Respuesta inesperada del bridge: {data!r}")

        entry = data[0]
        if "error" in entry:
            error = entry["error"]
            if error.get("type") == 101:
                raise LinkButtonNotPressed(error.get("description", "boton no pulsado"))
            raise BridgeError(f"El bridge rechazo el registro: {error}")

        success = entry.get("success", {})
        username, clientkey = success.get("username"), success.get("clientkey")
        if not username or not clientkey:
            raise BridgeError(
                "El bridge emitio username pero no clientkey. Firmware antiguo: "
                "sin clientkey no se puede usar la Entertainment API."
            )
        return username, clientkey

    # --- CLIP v2 ------------------------------------------------------------

    def get_entertainment_areas(self) -> list[EntertainmentArea]:
        data = self._request("GET", "/clip/v2/resource/entertainment_configuration")
        areas = []
        for item in data.get("data", []):
            areas.append(
                EntertainmentArea(
                    id=item["id"],
                    name=item.get("metadata", {}).get("name", "(sin nombre)"),
                    channel_count=len(item.get("channels", [])),
                    status=item.get("status", "unknown"),
                )
            )
        return areas

    def set_streaming(self, area_id: str, active: bool) -> None:
        """Arranca o para la sesion de streaming de una entertainment area.

        Obligatorio: el bridge no abre el puerto DTLS hasta que se le pide por
        aqui, y hay que mandar `stop` al salir o el area se queda ocupada.
        """
        self._request(
            "PUT",
            f"/clip/v2/resource/entertainment_configuration/{area_id}",
            json={"action": "start" if active else "stop"},
        )

    def get_bridge_info(self) -> dict:
        data = self._request("GET", "/clip/v2/resource/bridge")
        entries = data.get("data", [])
        return entries[0] if entries else {}
