"""Interfaz gráfica de la aplicación de subtítulos automáticos."""

from __future__ import annotations

import os
import sys


def icon_path() -> str:
    """Devuelve la ruta al icono de la app (sirve en desarrollo y en el .exe)."""
    candidates = []

    # Empaquetado con PyInstaller: junto al exe o en _MEIPASS.
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        candidates.append(os.path.join(base, "app_icon.ico"))
        candidates.append(os.path.join(base, "assets", "app_icon.ico"))

    # Desarrollo: carpeta assets del proyecto.
    candidates.append(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "app_icon.ico")
    )

    for c in candidates:
        if os.path.exists(c):
            return c
    return ""
