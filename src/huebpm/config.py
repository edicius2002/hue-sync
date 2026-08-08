"""Carga de configuracion.

`config.yaml` lleva los parametros ajustables. `hue_config.json` lleva las
credenciales del bridge y nunca se versiona ni se hardcodea en el codigo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_HUE_CONFIG_PATH = PROJECT_ROOT / "hue_config.json"


@dataclass
class AudioConfig:
    blocksize: int = 256
    buffer_seconds: float = 10.0
    device_name: str | None = None
    """Subcadena del nombre del dispositivo loopback, p.ej. "JBL Charge 6".

    Preferible a device_index: los indices de WASAPI se renumeran en cuanto
    aparece o desaparece un dispositivo de audio, asi que un indice fijado en
    la configuracion deja de valer al conectar unos auriculares.
    """
    device_index: int | None = None
    """Tiene prioridad sobre device_name. None y sin nombre = el que el sistema
    tenga por defecto."""


@dataclass
class AnalysisConfig:
    fft_size: int = 1024
    hop: int = 256
    """A 48 kHz: 187.5 frames/s, o sea 5.3 ms de resolucion temporal."""

    band_edges: tuple[tuple[float, float], ...] = (
        (20.0, 250.0),
        (250.0, 2000.0),
        (2000.0, 16000.0),
    )

    low_cutoff_hz: float = 500.0
    """Corte del ODF de graves usado para seguir el tempo."""
    tempo_low_weight: float = 1.0
    tempo_full_weight: float = 0.3

    min_bpm: float = 60.0
    max_bpm: float = 180.0
    prior_bpm: float = 120.0
    prior_width: float = 0.9
    """Ancho del prior en octavas. Mas alto = menos sesgo hacia prior_bpm."""
    history_seconds: float = 6.0
    min_history_seconds: float = 3.0
    """Historia minima antes de la primera estimacion. La ventana crece sola
    hasta history_seconds; esperar a llenarla entera solo retrasa el enganche."""
    salience_scale: float = 10.0
    """Divisor del z-score robusto que produce la confianza. Mas bajo = mas
    generoso. Se calibra contra musica real, no contra el self-test."""
    estimate_interval: float = 0.5
    smoothing_seconds: float = 1.5
    """Ventana de la media movil que se resta a la ODF.

    Debe cubrir varios beats. Si se acerca a un periodo de beat funciona como
    un notch en la frecuencia del pulso y el detector se va a un submultiplo.
    """

    harmonics: tuple[tuple[int, float], ...] = ((2, 0.5), (3, 0.35), (4, 0.25))
    """Multiplos del lag candidato que refuerzan su puntuacion, con su peso.

    Incluir el 3 no es decorativo: distingue el pulso real de un candidato a
    1.5x. Para el verdadero, todos los multiplos enteros correlacionan; para
    uno a 1.5x solo lo hacen los pares (2x=3 beats si, 3x=4.5 beats no).
    """

    phase_gain: float = 0.45
    period_gain: float = 0.12
    min_confidence: float = 0.15
    """Por debajo de esto la estimacion se descarta. Medido sobre musica real:
    los pasajes turbios bajan a ~0.29, asi que 0.25 dejaba cero margen."""
    full_confidence: float = 0.6
    """A partir de aqui el PLL corrige con la ganancia completa."""

    band_peak_decay: float = 0.5
    band_attack: float = 0.005
    band_release: float = 0.15

    silence_rms: float = 1e-4
    silence_timeout: float = 2.0


@dataclass
class RenderConfig:
    fps: float = 50.0
    latency_compensation_ms: float = 120.0
    """Cuanto *antes* del beat se emite el comando.

    Cubre analisis + DTLS + el salto Zigbee del bridge. Se calibra a ojo
    contra las luces reales; 120 ms es un punto de partida razonable dado que
    el bridge solo empuja a Zigbee a 25 Hz.
    """


@dataclass
class EffectsConfig:
    mode: str = "combo"
    """combo | beat_flash | spectrum"""

    beat_attack: float = 0.08
    """Fraccion del beat que dura la subida ANTES del golpe.

    Es lo que convierte el flash en algo que se anticipa al ritmo en vez de
    reaccionar a el. Solo tiene sentido porque el BeatClock sabe cuando llega
    el proximo beat.
    """
    beat_decay: float = 4.0
    """Constante de caida tras el golpe, en unidades de 1/beat."""
    beat_floor: float = 0.12
    """Brillo entre golpes. A cero la luz parpadea de forma agresiva."""

    bass_color: tuple[float, float, float] = (1.0, 0.12, 0.0)
    mid_color: tuple[float, float, float] = (0.1, 1.0, 0.25)
    treble_color: tuple[float, float, float] = (0.25, 0.45, 1.0)

    idle_color: tuple[float, float, float] = (1.0, 0.55, 0.2)
    idle_brightness: float = 0.07
    """Estado en reposo cuando no suena nada: tenue y fijo, nunca apagado."""

    saturation_boost: float = 1.15
    """Las luces Hue lavan los colores; un poco de saturacion extra compensa."""


@dataclass
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    effects: EffectsConfig = field(default_factory=EffectsConfig)


def _apply(obj: Any, data: dict | None) -> Any:
    if not data:
        return obj
    known = {f.name for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Clave desconocida en config.yaml: {key}")
        if key == "band_edges":
            value = tuple(tuple(float(x) for x in pair) for pair in value)
        elif key == "harmonics":
            value = tuple((int(m), float(w)) for m, w in value)
        elif key.endswith("_color"):
            value = tuple(float(x) for x in value)
        setattr(obj, key, value)
    return obj


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg = Config()
    if not path.exists():
        return cfg
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _apply(cfg.audio, data.get("audio"))
    _apply(cfg.analysis, data.get("analysis"))
    _apply(cfg.render, data.get("render"))
    _apply(cfg.effects, data.get("effects"))
    return cfg


@dataclass(frozen=True)
class HueCredentials:
    bridge_ip: str
    username: str
    clientkey: str
    entertainment_area_id: str | None = None


def load_hue_credentials(path: Path | str | None = None) -> HueCredentials:
    path = Path(path) if path else DEFAULT_HUE_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Ejecuta 'python run.py register' con el boton "
            "del bridge presionado para generarlo."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    missing = {"bridge_ip", "username", "clientkey"} - data.keys()
    if missing:
        raise ValueError(f"Faltan claves en {path}: {sorted(missing)}")
    return HueCredentials(
        bridge_ip=data["bridge_ip"],
        username=data["username"],
        clientkey=data["clientkey"],
        entertainment_area_id=data.get("entertainment_area_id"),
    )
