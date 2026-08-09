"""Tests de carga de configuracion.

Lo mas valioso aqui es que una clave desconocida **falle en voz alta**. Un
typo silenciosamente ignorado en config.yaml significa horas afinando un
parametro que nunca se estaba aplicando.
"""

from __future__ import annotations

import json

import pytest

from huebpm.config import (
    AnalysisConfig,
    Config,
    EffectsConfig,
    load_config,
    load_hue_credentials,
)


def escribir(tmp_path, texto: str):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_sin_fichero_usa_los_valores_por_defecto(tmp_path):
    cfg = load_config(tmp_path / "no_existe.yaml")
    assert isinstance(cfg, Config)
    assert cfg.analysis == AnalysisConfig()
    assert cfg.effects == EffectsConfig()


def test_carga_valores_del_yaml(tmp_path):
    ruta = escribir(tmp_path, """
audio:
  blocksize: 512
analysis:
  min_bpm: 70.0
  max_bpm: 190.0
render:
  fps: 40.0
effects:
  mode: beat_flash
""")
    cfg = load_config(ruta)
    assert cfg.audio.blocksize == 512
    assert cfg.analysis.min_bpm == 70.0
    assert cfg.analysis.max_bpm == 190.0
    assert cfg.render.fps == 40.0
    assert cfg.effects.mode == "beat_flash"


def test_clave_desconocida_falla_en_voz_alta(tmp_path):
    ruta = escribir(tmp_path, "analysis:\n  min_bmp: 70.0\n")  # typo a proposito
    with pytest.raises(ValueError, match="min_bmp"):
        load_config(ruta)


def test_yaml_vacio_no_revienta(tmp_path):
    assert load_config(escribir(tmp_path, "")).analysis == AnalysisConfig()


def test_seccion_ausente_conserva_defectos(tmp_path):
    cfg = load_config(escribir(tmp_path, "audio:\n  blocksize: 128\n"))
    assert cfg.audio.blocksize == 128
    assert cfg.effects == EffectsConfig()


def test_band_edges_se_convierten_a_tuplas(tmp_path):
    ruta = escribir(tmp_path, """
analysis:
  band_edges:
    - [30.0, 200.0]
    - [200.0, 1800.0]
""")
    edges = load_config(ruta).analysis.band_edges
    assert isinstance(edges, tuple)
    assert all(isinstance(par, tuple) for par in edges)
    assert edges[0] == (30.0, 200.0)


def test_harmonics_se_convierten_a_tuplas(tmp_path):
    ruta = escribir(tmp_path, "analysis:\n  harmonics:\n    - [2, 0.5]\n    - [3, 0.25]\n")
    arm = load_config(ruta).analysis.harmonics
    assert arm == ((2, 0.5), (3, 0.25))
    assert isinstance(arm[0][0], int)
    assert isinstance(arm[0][1], float)


def test_colores_se_convierten_a_tuplas(tmp_path):
    ruta = escribir(tmp_path, "effects:\n  bass_color: [0.9, 0.2, 0.1]\n")
    color = load_config(ruta).effects.bass_color
    assert isinstance(color, tuple)
    assert color == (0.9, 0.2, 0.1)


def test_el_config_del_repo_carga():
    """El config.yaml versionado debe ser valido: si se anade un campo al
    dataclass y no al yaml (o al reves), esto lo detecta."""
    cfg = load_config()
    assert cfg.render.fps > 0
    assert cfg.effects.mode in ("combo", "beat_flash", "spectrum")


def test_credenciales_sin_fichero_dan_error_accionable(tmp_path):
    with pytest.raises(FileNotFoundError, match="register"):
        load_hue_credentials(tmp_path / "no_existe.json")


def test_credenciales_incompletas_dicen_que_falta(tmp_path):
    ruta = tmp_path / "hue_config.json"
    ruta.write_text(json.dumps({"bridge_ip": "1.2.3.4"}), encoding="utf-8")
    with pytest.raises(ValueError, match="clientkey"):
        load_hue_credentials(ruta)


def test_credenciales_completas(tmp_path):
    ruta = tmp_path / "hue_config.json"
    ruta.write_text(
        json.dumps({
            "bridge_ip": "192.168.1.9",
            "username": "u" * 40,
            "clientkey": "a" * 32,
            "entertainment_area_id": "id-area",
        }),
        encoding="utf-8",
    )
    creds = load_hue_credentials(ruta)
    assert creds.bridge_ip == "192.168.1.9"
    assert creds.entertainment_area_id == "id-area"


def test_area_id_es_opcional(tmp_path):
    ruta = tmp_path / "hue_config.json"
    ruta.write_text(
        json.dumps({"bridge_ip": "1.2.3.4", "username": "u", "clientkey": "k"}),
        encoding="utf-8",
    )
    assert load_hue_credentials(ruta).entertainment_area_id is None
