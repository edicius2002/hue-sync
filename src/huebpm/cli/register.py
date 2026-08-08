"""Registro de credenciales contra el bridge.

Se ejecuta una sola vez. Escribe `hue_config.json` con bridge_ip, username y
clientkey; a partir de ahi el resto del proyecto lo lee de ahi y nunca
hardcodea nada.

El bridge solo emite credenciales durante ~30 s despues de pulsar su boton
fisico, asi que esto no se puede automatizar del todo: hay que ir y apretarlo.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..hue.rest import BridgeClient, BridgeError, LinkButtonNotPressed

POLL_INTERVAL = 2.0
POLL_TIMEOUT = 60.0


def _write_config(path: Path, ip: str, username: str, clientkey: str) -> None:
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    existing.update({"bridge_ip": ip, "username": username, "clientkey": clientkey})
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def run_register(
    ip: str,
    config_path: Path,
    force: bool = False,
    timeout: float = POLL_TIMEOUT,
) -> int:
    if config_path.exists() and not force:
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if data.get("username") and data.get("clientkey"):
            print(f"Ya existen credenciales en {config_path}.")
            print("El registro requiere pulsar el boton fisico del bridge, asi que")
            print("no se rehace solo. Usa --force si de verdad quieres regenerarlas.")
            return 1

    client = BridgeClient(ip)
    print(f"Bridge: {ip}")
    print(f"devicetype: {client.default_devicetype()}")
    print()
    print(">>> Pulsa AHORA el boton redondo del bridge. <<<")
    print(f"    Esperando hasta {timeout:.0f} s...")
    print()

    deadline = time.monotonic() + timeout
    username = clientkey = None
    while time.monotonic() < deadline:
        try:
            username, clientkey = client.create_user()
            break
        except LinkButtonNotPressed:
            remaining = deadline - time.monotonic()
            print(f"\r    boton sin pulsar, reintentando ({remaining:4.0f} s)", end="", flush=True)
            time.sleep(POLL_INTERVAL)
        except BridgeError as exc:
            print(f"\n{exc}")
            return 1

    print()
    if not username or not clientkey:
        print("Se agoto el tiempo. El bridge solo acepta el registro durante unos")
        print("30 s despues de pulsar el boton; vuelve a lanzarlo y pulsa entonces.")
        return 1

    _write_config(config_path, ip, username, clientkey)
    print(f"Credenciales guardadas en {config_path}")
    print(f"  username:  {username[:8]}...{username[-4:]}  ({len(username)} chars)")
    print(f"  clientkey: {'*' * 8}...  ({len(clientkey)} chars, PSK del handshake DTLS)")
    print()

    # Verificacion inmediata: si las credenciales sirven, esto responde. Y de
    # paso saca el id de la entertainment area, que hace falta para la Fase 2.
    client.username = username
    try:
        areas = client.get_entertainment_areas()
    except BridgeError as exc:
        print(f"Credenciales guardadas, pero fallo la verificacion: {exc}")
        return 1

    if not areas:
        print("AVISO: el bridge no tiene ninguna entertainment area configurada.")
        print("Creala desde la app movil de Hue (Configuracion > Entertainment areas)")
        print("y colocando las luces en el espacio 3D.")
        return 0

    print(f"Entertainment areas encontradas ({len(areas)}):")
    for area in areas:
        mark = "  (en uso)" if area.active else ""
        print(f"  {area.id}  {area.name!r}  {area.channel_count} canales{mark}")

    if len(areas) == 1:
        _patch(config_path, "entertainment_area_id", areas[0].id)
        print(f"\nGuardada como area por defecto: {areas[0].name!r}")
    else:
        print("\nHay varias. Elige una y ponla en hue_config.json como:")
        print('  "entertainment_area_id": "<el id de arriba>"')
    return 0


def _patch(path: Path, key: str, value: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_areas(ip: str, username: str) -> int:
    """Lista las entertainment areas de un bridge ya registrado."""
    client = BridgeClient(ip, username=username)
    try:
        areas = client.get_entertainment_areas()
    except BridgeError as exc:
        print(exc)
        return 1
    if not areas:
        print("No hay entertainment areas. Creala desde la app movil de Hue.")
        return 1
    for area in areas:
        mark = "  (en uso)" if area.active else ""
        print(f"{area.id}  {area.name!r}  {area.channel_count} canales{mark}")
    return 0
