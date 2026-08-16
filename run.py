"""Punto de entrada del MVP.

Analisis (no necesita el bridge):

    python run.py selftest              valida el detector con ground truth sintetico
    python run.py monitor               BPM y beats en vivo del audio del sistema
    python run.py devices               lista los dispositivos loopback WASAPI
    python run.py record out.wav        graba el audio del sistema
    python run.py analyze out.wav       analiza un WAV con diagnostico

Sincronizacion (lo principal):

    python run.py sync                  luces sincronizadas con lo que suena
    python run.py sync --dry-run        igual pero sin bridge, solo consola

Bridge (setup, una sola vez):

    python run.py register --ip <ip>    registra credenciales (boton del bridge)
    python run.py areas                 lista las entertainment areas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from huebpm.config import load_config  # noqa: E402


def _warn_if_wrong_python() -> None:
    """Avisa si se lanzo con el Python del sistema en vez del del entorno.

    Es el error mas facil de cometer aqui: media dependencia esta en los dos
    sitios, asi que el script arranca y solo revienta a mitad, con un
    ModuleNotFoundError que no apunta a la causa real.
    """
    venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return
    if Path(sys.prefix).resolve() == (PROJECT_DIR / ".venv").resolve():
        return
    print(
        f"AVISO: estas usando {sys.executable}\n"
        f"       y el entorno del proyecto es {venv_python}\n"
        f"       Si algo falla por un modulo que falta, esta es la causa.\n",
        file=sys.stderr,
    )


def main() -> int:
    _warn_if_wrong_python()
    parser = argparse.ArgumentParser(prog="run.py", description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="ruta a config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_self = sub.add_parser("selftest", help="valida el detector sin audio real")
    p_self.add_argument("--duration", type=float, default=30.0)

    p_mon = sub.add_parser("monitor", help="monitor de BPM en vivo")
    p_mon.add_argument("--duration", type=float, default=None)

    sub.add_parser("devices", help="lista dispositivos loopback WASAPI")

    p_reg = sub.add_parser("register", help="registra credenciales contra el bridge")
    p_reg.add_argument("--ip", required=True, help="IP del bridge en la red local")
    p_reg.add_argument("--force", action="store_true", help="regenera aunque ya existan")
    p_reg.add_argument("--timeout", type=float, default=60.0)

    sub.add_parser("areas", help="lista las entertainment areas del bridge")

    p_ht = sub.add_parser("huetest", help="prueba el canal DTLS a las luces")
    p_ht.add_argument("--seconds", type=float, default=20.0)
    p_ht.add_argument("--area", default=None, help="id del area (por defecto el de hue_config)")

    p_sync = sub.add_parser("sync", help="sincroniza las luces con el audio")
    p_sync.add_argument("--duration", type=float, default=None)
    p_sync.add_argument(
        "--mode",
        default=None,
        help="combo | harmony | bars | beat_flash | spectrum | sustain | dual | idle",
    )
    p_sync.add_argument("--area", default=None)
    p_sync.add_argument("--dry-run", action="store_true", help="sin bridge, solo consola")

    p_rec = sub.add_parser("record", help="graba el audio del sistema a WAV")
    p_rec.add_argument("out", type=Path)
    p_rec.add_argument("--seconds", type=float, default=25.0)

    p_an = sub.add_parser("analyze", help="analiza un WAV con diagnostico")
    p_an.add_argument("wav", type=Path)
    p_an.add_argument("--bpm", type=float, default=None, help="BPM real, para comparar")
    p_an.add_argument("--start", type=float, default=0.0, help="saltar N segundos")
    p_an.add_argument("--duration", type=float, default=None, help="analizar solo N segundos")

    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
    except ValueError as exc:
        # Errores de configuracion: el usuario necesita el mensaje, no la pila.
        print(exc, file=sys.stderr)
        return 2

    if args.command == "selftest":
        from huebpm.cli.selftest import run_selftest

        return run_selftest(cfg, duration=args.duration)

    if args.command == "monitor":
        from huebpm.cli.monitor import run_monitor

        return run_monitor(cfg, duration=args.duration)

    if args.command == "register":
        from huebpm.cli.register import run_register
        from huebpm.config import DEFAULT_HUE_CONFIG_PATH

        return run_register(args.ip, DEFAULT_HUE_CONFIG_PATH, args.force, args.timeout)

    if args.command == "areas":
        from huebpm.cli.register import run_areas
        from huebpm.config import load_hue_credentials

        try:
            creds = load_hue_credentials()
        except (FileNotFoundError, ValueError) as exc:
            print(exc)
            return 1
        return run_areas(creds.bridge_ip, creds.username)

    if args.command == "huetest":
        from huebpm.cli.huetest import run_huetest

        return run_huetest(cfg, args.seconds, args.area)

    if args.command == "sync":
        from huebpm.cli.sync import run_sync

        return run_sync(cfg, args.duration, args.mode, args.area, args.dry_run)

    if args.command == "record":
        from huebpm.cli.record import run_record

        return run_record(cfg, args.out, args.seconds)

    if args.command == "analyze":
        from huebpm.cli.analyze import run_analyze

        return run_analyze(cfg, args.wav, args.bpm, args.start, args.duration)

    if args.command == "devices":
        from huebpm.audio.capture import find_default_loopback, list_loopback_devices

        default = find_default_loopback()
        for d in list_loopback_devices():
            mark = "*" if d.index == default.index else " "
            print(f"{mark} [{d.index:>3}] {d.name}  ({d.samplerate} Hz, {d.channels} ch)")
        print("\n* = dispositivo por defecto")
        return 0

    parser.error("comando desconocido")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
