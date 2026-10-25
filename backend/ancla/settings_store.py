"""Configuración local. Un archivo dañado no se reemplaza en silencio."""

from __future__ import annotations

import os
from pathlib import Path

from ancla.models import ScanSettings


class SettingsError(RuntimeError):
    pass


def load_settings() -> ScanSettings:
    path = settings_path()
    if not path.exists():
        return ScanSettings()
    try:
        return ScanSettings.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SettingsError(f"No se pudo leer la configuración: {exc}") from exc


def save_settings(settings: ScanSettings) -> ScanSettings:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    return settings


def settings_path() -> Path:
    root = Path(os.environ["ANCLA_HOME"]) if os.environ.get("ANCLA_HOME") else project_root()
    return root / "data" / "settings.json"


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "backend").exists():
            return candidate
    return Path.cwd()
