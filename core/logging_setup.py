"""Configuración de logging de la app (archivo de log local)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def log_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "SubtitulosAutomaticos" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return log_dir() / "app.log"


_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger("subtitulos")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(log_file(), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # stderr solo para depuración; no se usa en el exe con ventana.
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    logger.addHandler(sh)


def get_logger(name: str = "subtitulos") -> logging.Logger:
    setup_logging()
    if name == "subtitulos":
        return logging.getLogger("subtitulos")
    return logging.getLogger(f"subtitulos.{name}")
