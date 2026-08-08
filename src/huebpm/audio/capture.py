"""Captura loopback WASAPI (audio de salida del sistema) en Windows.

Usa PyAudioWPatch, que es un fork de PortAudio con soporte de dispositivos
loopback. El callback solo hace downmix a mono y escribe al ring buffer: nada
de analisis aqui dentro, o PortAudio empieza a soltar bloques.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Falta PyAudioWPatch. Instala con: pip install PyAudioWPatch"
    ) from exc

from .ringbuffer import RingBuffer


@dataclass
class DeviceInfo:
    index: int
    name: str
    samplerate: int
    channels: int


def _to_device_info(raw: dict) -> DeviceInfo:
    return DeviceInfo(
        index=int(raw["index"]),
        name=str(raw["name"]),
        samplerate=int(raw["defaultSampleRate"]),
        channels=int(raw["maxInputChannels"]),
    )


def list_loopback_devices() -> list[DeviceInfo]:
    """Todos los dispositivos loopback WASAPI disponibles."""
    with pyaudio.PyAudio() as pa:
        return [_to_device_info(d) for d in pa.get_loopback_device_info_generator()]


def _describe(devices: list[DeviceInfo]) -> str:
    return "\n".join(f"  [{d.index:>3}] {d.name}" for d in devices)


def get_device(index: int) -> DeviceInfo:
    """Dispositivo loopback por indice.

    Ojo: los indices de WASAPI NO son estables. Se renumeran en cuanto
    aparece o desaparece un dispositivo (conectar un altavoz Bluetooth basta),
    asi que fijar un indice en la configuracion es fragil. Prefiere device_name.
    """
    devices = list_loopback_devices()
    for d in devices:
        if d.index == index:
            return d
    raise ValueError(
        f"El indice {index} ya no corresponde a ningun dispositivo loopback.\n"
        f"Los indices de WASAPI se renumeran solos; usa audio.device_name en "
        f"config.yaml, que es estable.\nDisponibles ahora:\n{_describe(devices)}"
    )


def find_by_name(fragment: str) -> DeviceInfo:
    """Primer loopback cuyo nombre contenga `fragment` (sin distinguir mayusculas)."""
    devices = list_loopback_devices()
    needle = fragment.casefold()
    matches = [d for d in devices if needle in d.name.casefold()]
    if not matches:
        raise ValueError(
            f"Ningun dispositivo loopback contiene {fragment!r}.\n"
            f"Disponibles:\n{_describe(devices)}"
        )
    return matches[0]


def resolve_device(index: int | None, name: str | None = None) -> DeviceInfo:
    if index is not None:
        return get_device(index)
    if name:
        return find_by_name(name)
    return find_default_loopback()


def find_default_loopback() -> DeviceInfo:
    """Dispositivo loopback que corresponde a los altavoces por defecto."""
    with pyaudio.PyAudio() as pa:
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError as exc:
            raise RuntimeError("WASAPI no disponible en este sistema") from exc

        speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if speakers.get("isLoopbackDevice"):
            return _to_device_info(speakers)

        for loopback in pa.get_loopback_device_info_generator():
            if speakers["name"] in loopback["name"]:
                return _to_device_info(loopback)

    raise RuntimeError(
        f"No se encontro loopback para el dispositivo de salida '{speakers['name']}'"
    )


class LoopbackCapture:
    """Stream de captura loopback que alimenta un RingBuffer mono.

    Nota: WASAPI en modo compartido impone el sample rate nativo del
    dispositivo (normalmente 48000). No se fuerza 44100 — se descubre y se
    propaga al analizador.
    """

    def __init__(
        self,
        device: DeviceInfo | None = None,
        blocksize: int = 256,
        buffer_seconds: float = 10.0,
    ) -> None:
        self.device = device or find_default_loopback()
        self.blocksize = blocksize
        self.samplerate = self.device.samplerate
        self.channels = self.device.channels
        self.buffer = RingBuffer(int(self.samplerate * buffer_seconds))

        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self.overflows = 0

    def _callback(self, in_data, frame_count, time_info, status):  # noqa: ANN001
        if status:
            self.overflows += 1
        samples = np.frombuffer(in_data, dtype=np.float32)
        if self.channels > 1:
            samples = samples.reshape(-1, self.channels).mean(axis=1)
        self.buffer.write(samples)
        return (None, pyaudio.paContinue)

    def start(self) -> None:
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paFloat32,
            channels=self.channels,
            rate=self.samplerate,
            input=True,
            input_device_index=self.device.index,
            frames_per_buffer=self.blocksize,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def __enter__(self) -> LoopbackCapture:
        self.start()
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.stop()
