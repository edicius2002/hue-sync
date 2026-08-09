"""Tests del ciclo de vida de la sesion de Entertainment.

Los 17 manejadores de error de `hue/` nunca se habian ejercitado. Lo que mas
importa aqui son dos invariantes:

1. El `action: stop` se manda **siempre** al cerrar. Si no, el area se queda
   ocupada y la siguiente sesion falla.
2. `send()` **nunca lanza**. Vive en un loop a 50 Hz y una excepcion por frame
   perdido tumbaria la aplicacion entera.
"""

from __future__ import annotations

import pytest
from fakes import FakeBackend, FakeRest

from huebpm.hue.backends import StreamError
from huebpm.hue.rest import BridgeError, EntertainmentArea

COLOR = {0: (1.0, 0.5, 0.0)}


def area(status: str = "inactive", channels: int = 3) -> EntertainmentArea:
    return EntertainmentArea(id="area-1", name="salon", channel_count=channels, status=status)


# --- arranque ----------------------------------------------------------------


def test_arranque_correcto(session, backend, rest):
    session.start()
    assert backend.connected
    assert rest.actions == [("area-1", True)]
    assert session.channel_count == 3


def test_area_inexistente_lista_las_disponibles(session, rest):
    rest.areas = [EntertainmentArea(id="otra", name="x", channel_count=1, status="inactive")]
    with pytest.raises(BridgeError, match="otra"):
        session.start()


def test_sin_areas_el_mensaje_lo_dice(session, rest):
    rest.areas = []
    with pytest.raises(BridgeError, match="ninguna"):
        session.start()


def test_area_ocupada_se_reclama_parando_primero(session, rest, backend):
    """Otra app (Hue Sync, o una que murio sin mandar stop) tiene la sesion.
    Hay que cerrarla antes de reclamarla."""
    rest.areas = [area(status="active")]
    session.start()
    assert rest.actions == [("area-1", False), ("area-1", True)]
    assert backend.connected


def test_reintenta_el_handshake_antes_de_rendirse(session, backend):
    backend.fail_connect = 2  # falla dos veces, engancha a la tercera
    session.start()
    assert backend.connected
    assert backend.connects == 3


def test_si_el_handshake_no_engancha_se_libera_el_area(session, backend, rest):
    """Dejar el area en 'active' tras un fallo la bloquearia para todos."""
    backend.fail_connect = 99
    with pytest.raises(StreamError):
        session.start()
    assert rest.actions[-1] == ("area-1", False)
    assert not backend.connected


# --- cierre ------------------------------------------------------------------


def test_stop_cierra_backend_y_libera_el_area(session, backend, rest):
    session.start()
    session.stop()
    assert backend.closes == 1
    assert rest.actions[-1] == ("area-1", False)


def test_stop_es_idempotente(session, rest):
    session.start()
    session.stop()
    session.stop()
    assert rest.actions.count(("area-1", False)) == 1


def test_stop_no_propaga_si_el_bridge_ya_no_responde(session, backend):
    """Se llama desde un `finally`: dejar escapar una excepcion aqui ocultaria
    la causa real del cierre."""
    session.start()
    session.rest = FakeRest(fail_stop=True)
    session.stop()  # no debe lanzar
    assert backend.closes == 1


def test_sin_start_no_se_manda_stop(session, rest):
    session.stop()
    assert rest.actions == []


def test_context_manager(backend, rest):
    from huebpm.hue.client import EntertainmentSession

    s = EntertainmentSession("1.2.3.4", "u", "k", "area-1",
                             backend=backend, start_delay=0.0, reconnect_delay=0.0)
    s.rest = rest
    with s:
        assert backend.connected
    assert not backend.connected
    assert rest.actions[-1] == ("area-1", False)


# --- envio -------------------------------------------------------------------


def test_send_correcto(session, backend):
    session.start()
    assert session.send(COLOR) is True
    assert backend.sent == [COLOR]


def test_send_devuelve_false_en_vez_de_lanzar(session, backend):
    """El invariante que protege el loop de render a 50 Hz."""
    session.start()
    backend.fail_send = True
    assert session.send(COLOR) is False


def test_send_sin_start_reclama_el_area_y_la_libera(session, backend, rest):
    """Regresion: `send()` sin `start()` previo se auto-conecta via
    `_try_reconnect`, que pide `action: start` al bridge. Si eso no queda
    registrado, `stop()` se salta la liberacion y el area queda ocupada
    indefinidamente, que es justo el estado que bloquea al siguiente cliente."""
    assert session.send(COLOR) is True
    assert ("area-1", True) in rest.actions

    session.stop()
    assert rest.actions[-1] == ("area-1", False), "el area tiene que quedar libre"
    assert backend.closes >= 1


def test_send_reconecta_tras_una_caida(session, backend, rest):
    session.start()
    session.send(COLOR)
    backend.drop()  # se cae sin avisar

    assert session.send(COLOR) is True
    assert backend.connects == 2
    assert rest.actions[-1] == ("area-1", True), "rehace el action:start"


def test_la_reconexion_se_limita_en_frecuencia(backend, rest):
    """A 50 Hz, reintentar en cada frame martillearia el bridge."""
    from huebpm.hue.client import EntertainmentSession

    s = EntertainmentSession("1.2.3.4", "u", "k", "area-1",
                             backend=backend, start_delay=0.0, reconnect_delay=60.0)
    s.rest = rest
    s.start()
    backend.drop()
    backend.fail_connect = 99

    for _ in range(50):
        s.send(COLOR)
    assert backend.connects <= 2, "solo un intento dentro de la ventana"


def test_la_reconexion_fallida_no_propaga(session, backend):
    session.start()
    backend.drop()
    backend.fail_connect = 99
    assert session.send(COLOR) is False  # no lanza


# --- keepalive ---------------------------------------------------------------


def test_keepalive_no_hace_nada_sin_frame_previo(session, backend):
    session.start()
    session.keepalive()
    assert backend.sent == []


def test_keepalive_no_reenvia_antes_de_tiempo(session, backend):
    session.start()
    session.send(COLOR)
    session.keepalive()
    assert len(backend.sent) == 1


def test_keepalive_reenvia_el_ultimo_frame(session, backend, monkeypatch):
    """El bridge cierra la sesion si deja de recibir paquetes ~10 s."""
    import huebpm.hue.client as client_mod

    # El reloj se sustituye ANTES del primer envio: si no, `_last_send`
    # quedaria grabado con el reloj real y la comparacion no tendria sentido.
    reloj = [1000.0]
    monkeypatch.setattr(client_mod.time, "monotonic", lambda: reloj[0])

    session.start()
    session.send(COLOR)

    reloj[0] += client_mod.KEEPALIVE_INTERVAL + 1.0
    session.keepalive()

    assert len(backend.sent) == 2
    assert backend.sent[-1] == COLOR


# --- backend -----------------------------------------------------------------


@pytest.mark.parametrize("valor,esperado", [
    (-1.0, 0), (0.0, 0), (0.5, 32767), (1.0, 65535), (2.0, 65535),
])
def test_conversion_a_16_bits_satura(valor, esperado):
    from huebpm.hue.backends import _to_u16

    assert _to_u16(valor) == esperado


def test_backend_desconocido_lista_las_opciones():
    from huebpm.hue.backends import make_backend

    with pytest.raises(ValueError, match="pure"):
        make_backend("noexiste")


def test_backend_sin_conectar_no_envia():
    from huebpm.hue.backends import PurePythonBackend

    b = PurePythonBackend()
    assert not b.connected
    with pytest.raises(StreamError, match="no conectado"):
        b.send(COLOR)


def test_falta_de_libreria_da_error_accionable(monkeypatch):
    """Es el sintoma de lanzar con el Python del sistema, y el mensaje por
    defecto de Python no lo dice."""
    import builtins

    from huebpm.hue.backends import PurePythonBackend

    real_import = builtins.__import__

    def sin_hue_entertainment(name, *args, **kwargs):
        if name.startswith("hue_entertainment"):
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_hue_entertainment)
    with pytest.raises(StreamError, match="venv"):
        PurePythonBackend().connect("1.2.3.4", "u", "k", "area")


def test_close_es_seguro_sin_conectar():
    from huebpm.hue.backends import PurePythonBackend

    PurePythonBackend().close()  # no debe lanzar


def test_el_fake_backend_cumple_el_protocolo():
    """Si el protocolo cambia, esto avisa antes de que los demas tests mientan."""
    from huebpm.hue.backends import StreamBackend

    assert isinstance(FakeBackend(), StreamBackend)
