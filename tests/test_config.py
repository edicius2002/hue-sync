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
  sustain_window: 3.0
  sustain_transition: 1.2
  sustain_energy_full: 0.25
  sustain_energy_zero: 0.50
render:
  fps: 40.0
effects:
  mode: beat_flash
""")
    cfg = load_config(ruta)
    assert cfg.audio.blocksize == 512
    assert cfg.analysis.min_bpm == 70.0
    assert cfg.analysis.max_bpm == 190.0
    assert cfg.analysis.sustain_window == 3.0
    assert cfg.analysis.sustain_transition == 1.2
    assert cfg.analysis.sustain_energy_full == 0.25
    assert cfg.analysis.sustain_energy_zero == 0.50
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


# --- variables de entorno ----------------------------------------------------


def test_el_entorno_pisa_la_configuracion():
    from huebpm.config import Config, apply_env_overrides

    cfg = Config()
    aplicados = apply_env_overrides(cfg, {"HUEBPM_EFFECTS_ONSET_ACCENT": "0.42"})
    assert cfg.effects.onset_accent == 0.42
    assert aplicados == ["effects.onset_accent = 0.42"]


def test_se_ignora_lo_que_no_lleva_prefijo():
    from huebpm.config import Config, apply_env_overrides

    cfg = Config()
    assert apply_env_overrides(cfg, {"PATH": "/x", "ONSET_ACCENT": "9"}) == []


@pytest.mark.parametrize("campo,texto,esperado", [
    ("HUEBPM_RENDER_FPS", "40", 40.0),
    ("HUEBPM_AUDIO_BLOCKSIZE", "512", 512),
    ("HUEBPM_ANALYSIS_CHROMA_PEAKS_ONLY", "false", False),
    ("HUEBPM_AUDIO_DEVICE_NAME", "JBL Charge", "JBL Charge"),
    ("HUEBPM_AUDIO_DEVICE_INDEX", "27", 27),
    ("HUEBPM_AUDIO_DEVICE_INDEX", "none", None),
])
def test_coercion_de_tipos(campo, texto, esperado):
    from huebpm.config import Config, apply_env_overrides

    cfg = Config()
    apply_env_overrides(cfg, {campo: texto})
    seccion, nombre = campo[len("HUEBPM_"):].split("_", 1)
    assert getattr(getattr(cfg, seccion.lower()), nombre.lower()) == esperado


def test_una_variable_mal_escrita_falla_en_voz_alta():
    """El fallo silencioso mas caro: un ajuste que crees activo y no lo esta."""
    from huebpm.config import Config, apply_env_overrides

    cfg = Config()
    with pytest.raises(ValueError, match="onset_acento"):
        apply_env_overrides(cfg, {"HUEBPM_EFFECTS_ONSET_ACENTO": "0.5"})
    with pytest.raises(ValueError, match="seccion desconocida"):
        apply_env_overrides(cfg, {"HUEBPM_EFECTOS_ONSET_ACCENT": "0.5"})


def test_un_campo_desconocido_sugiere_el_parecido_y_dice_como_quitarlo(monkeypatch):
    """Una variable huerfana tumba CUALQUIER comando, asi que el mensaje tiene
    que decir como salir.

    Paso de verdad: al renombrar `channel_roles` a `channel_modes` quedo la
    variable de una prueba anterior en la sesion y el error decia solo que el
    campo no existia. Sin la sugerencia ni la salida, el usuario no tiene forma
    de saber que la puso el mismo.
    """
    monkeypatch.setenv("HUEBPM_EFFECTS_CHANNEL_ROLES", '["a","b"]')
    with pytest.raises(ValueError) as exc:
        load_config()
    mensaje = str(exc.value)
    assert "channel_modes" in mensaje, "no sugiere el campo nuevo"
    assert "set HUEBPM_EFFECTS_CHANNEL_ROLES=" in mensaje, "no dice como quitarla"


def test_un_campo_sin_parecido_no_inventa_sugerencia(monkeypatch):
    """La sugerencia solo aparece si de verdad se parece a algo."""
    monkeypatch.setenv("HUEBPM_EFFECTS_XYZZY", "1")
    with pytest.raises(ValueError) as exc:
        load_config()
    assert "Quiza querias" not in str(exc.value)
