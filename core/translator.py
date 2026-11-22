"""Traducción de textos de subtítulos usando Argos Translate (offline)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Idiomas destino soportados en la UI -> código Argos Translate
TARGET_LANGUAGES = {
    "original": {"label": "Mantener original", "argos": None},
    "en": {"label": "Inglés", "argos": "en"},
    "ja": {"label": "Japonés", "argos": "ja"},
    "zh": {"label": "Chino", "argos": "zh"},
    "fr": {"label": "Francés", "argos": "fr"},
    "pt": {"label": "Portugués", "argos": "pt"},
}


def _bundled_package_dirs() -> list[str]:
    """Posibles ubicaciones de paquetes Argos incluidos con la app."""
    dirs: list[str] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        exe_dir = Path(sys.executable).resolve().parent
        for root in (exe_dir, base):
            dirs.append(str(root / "argos-translate" / "packages"))
            dirs.append(str(root / "share" / "argos-translate" / "packages"))
    # Desarrollo: junto al proyecto o en la ubicación por defecto del usuario.
    project_root = Path(__file__).resolve().parent.parent
    dirs.append(str(project_root / "argos-translate" / "packages"))
    return [d for d in dirs if os.path.isdir(d)]


def _ensure_argos_configured() -> None:
    import argostranslate.settings as settings

    bundled = _bundled_package_dirs()
    if not bundled:
        return

    # Añadir directorios empaquetados donde Argos busca paquetes.
    current = list(getattr(settings, "package_dirs", []) or [])
    for d in bundled:
        if d not in current:
            current.append(d)
    settings.package_dirs = current

    # También establecer package_data_dir si el directorio por defecto no existe
    # y tenemos uno empaquetado.
    default_dir = getattr(settings, "package_data_dir", None)
    if default_dir and not os.path.isdir(default_dir) and bundled:
        settings.package_data_dir = bundled[0]


def translate_texts(texts: list[str], target_code: str) -> list[str]:
    """Traduce una lista de textos del inglés a `target_code` usando Argos.

    Si target_code es 'en' o no se puede traducir, devuelve los textos originales.
    """
    if target_code == "en" or not texts:
        return list(texts)

    try:
        import argostranslate.translate as argos_translate
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Argos Translate no está instalado. Ejecuta: pip install argostranslate"
        ) from exc

    _ensure_argos_configured()

    installed = argos_translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == "en"), None)
    to_lang = next((l for l in installed if l.code == target_code), None)

    if from_lang is None or to_lang is None:
        raise RuntimeError(
            f"No se encontró el paquete de traducción en-> {target_code}. "
            "Asegúrate de que el modelo de traducción esté instalado."
        )

    translation = from_lang.get_translation(to_lang)
    if translation is None:
        raise RuntimeError(
            f"No hay traducción disponible de en a {target_code}."
        )

    out: list[str] = []
    for text in texts:
        # Preservar texto vacío
        if not text.strip():
            out.append(text)
            continue
        try:
            out.append(translation.translate(text))
        except Exception:
            out.append(text)
    return out