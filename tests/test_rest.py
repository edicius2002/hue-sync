"""Tests del cliente CLIP v2 con `requests` mockeado.

Lo que se verifica no es el camino feliz —ese ya se probo contra el bridge
real— sino que **cada fallo produzca un mensaje accionable**. El volcado por
defecto de `requests` es una pared de texto que no dice lo que casi siempre
pasa de verdad: que la IP esta mal o que no se pulso el boton.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
import requests

from huebpm.hue.rest import BridgeClient, BridgeError, LinkButtonNotPressed


def respuesta(payload, status: int = 200):
    r = Mock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.json.return_value = payload
    r.text = json.dumps(payload)
    return r


def cliente(**kwargs) -> BridgeClient:
    return BridgeClient("192.168.1.9", **kwargs)


# --- mapeo de errores de red -------------------------------------------------


def test_timeout_menciona_la_ip_y_la_red():
    c = cliente()
    with (
        patch.object(c._session, "request", side_effect=requests.exceptions.ConnectTimeout()),
        pytest.raises(BridgeError, match="192.168.1.9"),
    ):
        c.get_bridge_info()


def test_connection_error_explica_donde_mirar():
    """Regresion: antes se propagaba el volcado crudo de requests, que ocupa
    diez lineas y no menciona la causa real."""
    c = cliente()
    with (
        patch.object(c._session, "request", side_effect=requests.exceptions.ConnectionError()),
        pytest.raises(BridgeError, match="app movil") as exc,
    ):
        c.get_bridge_info()
    assert "192.168.1.9" in str(exc.value)


def test_401_sugiere_volver_a_registrar():
    c = cliente(username="viejo")
    with (
        patch.object(c._session, "request", return_value=respuesta({}, status=401)),
        pytest.raises(BridgeError, match="registrar"),
    ):
        c.get_bridge_info()


def test_error_http_incluye_codigo_y_ruta():
    c = cliente(username="u")
    with (
        patch.object(c._session, "request", return_value=respuesta({"x": 1}, status=500)),
        pytest.raises(BridgeError, match="500"),
    ):
        c.get_bridge_info()


def test_la_verificacion_tls_esta_desactivada():
    """El bridge presenta un certificado autofirmado; verificar siempre falla.
    Es deliberado y conviene que quede fijado por un test."""
    assert cliente()._session.verify is False


def test_la_app_key_viaja_en_la_cabecera():
    c = cliente(username="clave-app")
    with patch.object(c._session, "request", return_value=respuesta({"data": []})) as req:
        c.get_entertainment_areas()
    assert req.call_args.kwargs["headers"]["hue-application-key"] == "clave-app"


def test_sin_username_no_se_manda_cabecera():
    c = cliente()
    with patch.object(c._session, "request", return_value=respuesta({"data": []})) as req:
        c.get_entertainment_areas()
    assert "hue-application-key" not in req.call_args.kwargs["headers"]


# --- registro ----------------------------------------------------------------


def test_boton_sin_pulsar_es_su_propia_excepcion():
    """Tiene que distinguirse de un error de verdad: el flujo de registro
    reintenta en bucle esperando a que el usuario llegue al bridge."""
    c = cliente()
    payload = [{"error": {"type": 101, "description": "link button not pressed"}}]
    with (
        patch.object(c._session, "request", return_value=respuesta(payload)),
        pytest.raises(LinkButtonNotPressed),
    ):
        c.create_user()


def test_otro_error_del_bridge_no_es_boton_sin_pulsar():
    c = cliente()
    payload = [{"error": {"type": 7, "description": "invalid value"}}]
    with (
        patch.object(c._session, "request", return_value=respuesta(payload)),
        pytest.raises(BridgeError) as exc,
    ):
        c.create_user()
    assert not isinstance(exc.value, LinkButtonNotPressed)


def test_registro_correcto_devuelve_credenciales():
    c = cliente()
    payload = [{"success": {"username": "u" * 40, "clientkey": "A" * 32}}]
    with patch.object(c._session, "request", return_value=respuesta(payload)):
        username, clientkey = c.create_user()
    assert username == "u" * 40
    assert clientkey == "A" * 32


def test_firmware_sin_clientkey_falla_explicando_por_que():
    """Un bridge viejo emite username pero no clientkey. Sin clientkey no hay
    PSK y por tanto no hay Entertainment API: hay que decirlo, no devolver
    unas credenciales que luego fallaran en el handshake."""
    c = cliente()
    payload = [{"success": {"username": "u" * 40}}]
    with (
        patch.object(c._session, "request", return_value=respuesta(payload)),
        pytest.raises(BridgeError, match="clientkey"),
    ):
        c.create_user()


def test_respuesta_con_forma_inesperada():
    c = cliente()
    with (
        patch.object(c._session, "request", return_value=respuesta({"raro": True})),
        pytest.raises(BridgeError, match="inesperada"),
    ):
        c.create_user()


def test_se_pide_clientkey_en_el_registro():
    c = cliente()
    payload = [{"success": {"username": "u", "clientkey": "k"}}]
    with patch.object(c._session, "request", return_value=respuesta(payload)) as req:
        c.create_user()
    assert req.call_args.kwargs["json"]["generateclientkey"] is True


def test_devicetype_respeta_el_limite_del_bridge():
    assert len(BridgeClient.default_devicetype()) <= 40
    assert "#" in BridgeClient.default_devicetype()


# --- entertainment areas -----------------------------------------------------


def test_parsea_las_areas():
    c = cliente(username="u")
    payload = {"data": [
        {"id": "a1", "metadata": {"name": "salon"},
         "channels": [{}, {}, {}], "status": "active"},
        {"id": "a2", "metadata": {"name": "bano"}, "channels": [{}], "status": "inactive"},
    ]}
    with patch.object(c._session, "request", return_value=respuesta(payload)):
        areas = c.get_entertainment_areas()
    assert [a.id for a in areas] == ["a1", "a2"]
    assert areas[0].channel_count == 3
    assert areas[0].active
    assert not areas[1].active


def test_area_sin_nombre_no_revienta():
    c = cliente(username="u")
    payload = {"data": [{"id": "a1", "metadata": {}, "channels": []}]}
    with patch.object(c._session, "request", return_value=respuesta(payload)):
        areas = c.get_entertainment_areas()
    assert areas[0].name == "(sin nombre)"
    assert areas[0].channel_count == 0


def test_sin_areas_devuelve_lista_vacia():
    c = cliente(username="u")
    with patch.object(c._session, "request", return_value=respuesta({"data": []})):
        assert c.get_entertainment_areas() == []


@pytest.mark.parametrize("activo,esperado", [(True, "start"), (False, "stop")])
def test_set_streaming_manda_la_accion_correcta(activo, esperado):
    c = cliente(username="u")
    with patch.object(c._session, "request", return_value=respuesta({"data": []})) as req:
        c.set_streaming("area-1", activo)
    assert req.call_args.kwargs["json"] == {"action": esperado}
    assert "area-1" in req.call_args.args[1]
    assert req.call_args.args[0] == "PUT"
