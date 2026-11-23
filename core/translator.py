"""Traducción de textos de subtítulos usando Argos Translate (offline).

Los idiomas (excepto original/inglés) se descargan bajo demanda.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable


# Idiomas destino soportados en la UI -> código Argos Translate
TARGET_LANGUAGES = {
    "original": {"label": "Mantener original", "argos": None},
    "en": {"label": "Inglés", "argos": "en"},
    "ja": {"label": "Japonés", "argos": "ja"},
    "zh": {"label": "Chino", "argos": "zh"},
    "fr": {"label": "Francés", "argos": "fr"},
    "pt": {"label": "Portugués", "argos": "pt"},
    "ko": {"label": "Coreano", "argos": "ko"},
}

# Idiomas que no requieren paquete Argos (Whisper los maneja directo)
BUILTIN_LANGUAGES = {"original", "en"}


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "SubtitulosAutomaticos"


def get_package_dir() -> Path:
    """Directorio donde se guardan paquetes Argos descargados por el usuario."""
    d = _app_data_dir() / "argos-packages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundled_package_dirs() -> list[Path]:
    """Posibles ubicaciones de paquetes Argos incluidos con la app."""
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        exe_dir = Path(sys.executable).resolve().parent
        for root in (exe_dir, base):
            dirs.append(root / "argos-translate" / "packages")
            dirs.append(root / "share" / "argos-translate" / "packages")
    project_root = Path(__file__).resolve().parent.parent
    dirs.append(project_root / "argos-translate" / "packages")
    return [d for d in dirs if d.is_dir()]


def _ensure_argos_configured() -> None:
    import argostranslate.settings as settings

    pkg_dir = get_package_dir()
    candidates = [pkg_dir] + _bundled_package_dirs()

    current = list(getattr(settings, "package_dirs", []) or [])
    current_strs = {str(p) for p in current}
    for d in candidates:
        sd = str(d)
        if sd not in current_strs:
            current.append(Path(sd))
            current_strs.add(sd)
    settings.package_dirs = current

    # Usar directorio escribible por el usuario para paquetes descargados
    settings.package_data_dir = Path(str(pkg_dir))


def is_language_installed(target_code: str) -> bool:
    """True si el idioma está listo (builtin o paquete Argos instalado)."""
    if target_code in BUILTIN_LANGUAGES:
        return True
    try:
        import argostranslate.translate as argos_translate
    except Exception:
        return False
    _ensure_argos_configured()
    try:
        installed = argos_translate.get_installed_languages()
        from_lang = next((l for l in installed if l.code == "en"), None)
        to_lang = next((l for l in installed if l.code == target_code), None)
        if from_lang is None or to_lang is None:
            return False
        return from_lang.get_translation(to_lang) is not None
    except Exception:
        return False


def download_language(
    target_code: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> None:
    """Descarga e instala el paquete Argos para traducir en->target_code."""
    if target_code in BUILTIN_LANGUAGES:
        return
    if is_language_installed(target_code):
        return

    try:
        import argostranslate.package as argos_package
    except Exception as exc:
        raise RuntimeError(
            "Argos Translate no está instalado. Ejecuta: pip install argostranslate"
        ) from exc

    _ensure_argos_configured()

    try:
        argos_package.update_package_index()
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo obtener la lista de paquetes de traducción: {exc}"
        ) from exc

    available = argos_package.get_available_packages()
    pkg = next(
        (p for p in available if p.from_code == "en" and p.to_code == target_code),
        None,
    )
    if pkg is None:
        raise RuntimeError(
            f"No se encontró paquete de traducción en -> {target_code}."
        )

    # Descargar con progreso
    download_path = None
    try:
        # argos package.download() doesn't expose progress; download manually.
        import urllib.request
        from argostranslate import settings as argos_settings

        url = pkg.links[0] if pkg.links else None
        if not url:
            download_path = Path(pkg.download())
        else:
            os.makedirs(argos_settings.downloads_dir, exist_ok=True)
            filename = url.split("/")[-1] or f"translate-en_{target_code}.argosmodel"
            download_path = Path(argos_settings.downloads_dir) / filename
            req = urllib.request.Request(url, headers={"User-Agent": "SubtitulosAutomaticos"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                chunk = 1024 * 256
                with open(download_path, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if progress_cb:
                            try:
                                progress_cb(downloaded, total)
                            except Exception:
                                pass

        argos_package.install_from_path(download_path)
    finally:
        if download_path and download_path.exists():
            try:
                download_path.unlink()
            except Exception:
                pass

    # Limpiar cache de idiomas instalados
    try:
        import argostranslate.translate as argos_translate
        argos_translate.get_installed_languages.cache_clear()
    except Exception:
        pass

    if not is_language_installed(target_code):
        raise RuntimeError(
            f"El paquete en -> {target_code} se descargó pero no se pudo activar."
        )


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
            f"No se encontró el paquete de traducción en -> {target_code}. "
            "Descárgalo desde la opción de idioma en la app."
        )

    translation = from_lang.get_translation(to_lang)
    if translation is None:
        raise RuntimeError(f"No hay traducción disponible de en a {target_code}.")

    out: list[str] = []
    for text in texts:
        if not text.strip():
            out.append(text)
            continue
        try:
            out.append(translation.translate(text))
        except Exception:
            out.append(text)
    return out
