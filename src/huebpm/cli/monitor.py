"""Monitor de consola: BPM y beats en vivo, sin necesidad del bridge.

Corre el mismo loop de render a tasa fija que usara el cliente Hue, asi que
tambien sirve para verificar el jitter del temporizador antes de meter DTLS en
la ecuacion.
"""

from __future__ import annotations

import ctypes
import sys
import time

from ..audio.capture import LoopbackCapture, resolve_device
from ..config import Config
from ..engine import AnalysisEngine, LiveAnalyzer
from ..timing import RateLimiter, TimerResolution

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
CYAN = "\x1b[36m"
WHITE = "\x1b[97m"


def _enable_vt() -> None:
    """Habilita secuencias ANSI en la consola clasica de Windows."""
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def _bar(value: float, width: int = 24, color: str = "") -> str:
    value = max(0.0, min(1.0, value))
    filled = int(round(value * width))
    return f"{color}{'█' * filled}{DIM}{'·' * (width - filled)}{RESET}"


def run_monitor(cfg: Config, duration: float | None = None) -> int:
    _enable_vt()

    device = resolve_device(cfg.audio.device_index, cfg.audio.device_name)
    print(f"{BOLD}Dispositivo:{RESET} [{device.index}] {device.name}")
    print(f"{DIM}{device.samplerate} Hz, {device.channels} canales, "
          f"bloque {cfg.audio.blocksize}{RESET}")

    capture = LoopbackCapture(
        device=device,
        blocksize=cfg.audio.blocksize,
        buffer_seconds=cfg.audio.buffer_seconds,
    )
    engine = AnalysisEngine(device.samplerate, cfg.analysis)
    analyzer = LiveAnalyzer(capture, engine)

    frame_ms = 1000.0 * cfg.analysis.hop / device.samplerate
    print(f"{DIM}ODF a {engine.spectral.frame_rate:.0f} fps ({frame_ms:.1f} ms), "
          f"render a {cfg.render.fps:.0f} Hz, "
          f"compensacion {cfg.render.latency_compensation_ms:.0f} ms{RESET}")
    print(f"{DIM}Ctrl-C para salir. Pon musica.{RESET}\n")

    lines = 7
    print("\n" * lines, end="")

    comp = cfg.render.latency_compensation_ms / 1000.0
    limiter = RateLimiter(cfg.render.fps)
    started = time.perf_counter()
    beat_flash_until = 0.0
    beat_count = 0
    # El loop corre a la tasa de render real (la que usara el envio DTLS), pero
    # la pantalla solo se redibuja a ~20 Hz: mas rapido no se percibe y llena
    # la terminal de escapes ANSI.
    redraw_interval = 0.05
    next_redraw = 0.0

    capture.start()
    analyzer.start()
    try:
        with TimerResolution(1):
            while True:
                now = limiter.tick()
                if duration and now - started > duration:
                    break

                st = engine.state
                clock = engine.clock

                # Se consulta el reloj en el futuro: es asi como el comando
                # sale *antes* del beat y llega a la luz justo a tiempo.
                lookahead = now + comp
                if clock.poll_beats(lookahead) > 0:
                    beat_flash_until = now + 0.09
                    beat_count += 1

                if now < next_redraw:
                    continue
                next_redraw = now + redraw_interval

                bpm = f"{st.bpm:6.1f}" if st.bpm else "  --  "
                if st.silent:
                    status = f"{DIM}SILENCIO{RESET}"
                elif clock.is_stale(lookahead):
                    status = f"{YELLOW}BUSCANDO{RESET}"
                else:
                    status = f"{GREEN}ENGANCHADO{RESET}"

                ttnb = clock.time_to_next_beat(lookahead)
                phase = clock.phase(lookahead)
                beat_on = now < beat_flash_until
                marker = f"{BOLD}{WHITE}◉{RESET}" if beat_on else f"{DIM}○{RESET}"

                bass, mid, treble = (list(st.bands) + [0, 0, 0])[:3]
                out = [
                    f"  {BOLD}BPM{RESET} {CYAN}{bpm}{RESET}   conf {_bar(st.confidence, 10, GREEN)} "
                    f"{st.confidence:4.2f}   {status}",
                    f"  beat  {marker}  {_bar(1.0 - phase, 24, WHITE)}  "
                    + (f"proximo en {ttnb * 1000:6.1f} ms" if ttnb is not None else "sin enganche"),
                    "",
                    f"  graves  {_bar(bass, 24, RED)}  {bass:4.2f}",
                    f"  medios  {_bar(mid, 24, GREEN)}  {mid:4.2f}",
                    f"  agudos  {_bar(treble, 24, BLUE)}  {treble:4.2f}",
                    f"  {DIM}beats {beat_count}   jitter render {limiter.jitter.mean_ms:.2f} ms "
                    f"(max {limiter.jitter.max_ms:.2f})   frames {st.frames_analyzed}   "
                    f"overflow {capture.overflows}{RESET}",
                ]
                sys.stdout.write(f"\x1b[{lines}A" + "".join(f"\x1b[2K{line}\n" for line in out))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        analyzer.stop()
        capture.stop()

    print(f"\n{DIM}Jitter medio del loop de render: {limiter.jitter.mean_ms:.2f} ms "
          f"(max {limiter.jitter.max_ms:.2f} ms) sobre {limiter.jitter.count} ticks{RESET}")
    return 0
