"""Comprobación y aplicación de actualizaciones desde GitHub Releases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .logging_setup import get_logger
from .version import APP_VERSION, GITHUB_RELEASES_URL

log = get_logger("updater")


def _parse_version(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.replace("-", ".").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # ignorar sufijos no numéricos
            num = ""
            for ch in p:
                if ch.isdigit():
                    num += ch
                else:
                    break
            if num:
                parts.append(int(num))
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SubtitulosAutomaticos/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(
    url: str,
    dest: Path,
    timeout: int = 60,
    progress_cb=None,
) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"SubtitulosAutomaticos/{APP_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk = 1024 * 256
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_for_update(timeout: int = 10) -> dict | None:
    """Consulta la última release en GitHub.

    Devuelve dict con {version, zip_url, sha256, notes, html_url} o None si
    no hay actualización / no se pudo comprobar.
    """
    try:
        release = _http_get_json(GITHUB_RELEASES_URL, timeout=timeout)
    except Exception:
        return None

    tag = str(release.get("tag_name", "")).strip()
    if not tag:
        return None
    if not is_newer(tag, APP_VERSION):
        return None

    assets = release.get("assets", []) or []
    zip_asset = None
    sha_asset = None
    info_asset = None
    for a in assets:
        name = str(a.get("name", "")).lower()
        if name == "app-update.zip":
            zip_asset = a
        elif name in ("app-update.zip.sha256", "app-update.sha256"):
            sha_asset = a
        elif name == "version.json":
            info_asset = a

    if not zip_asset:
        return None

    sha256 = ""
    if info_asset:
        try:
            info_path = Path(tempfile.gettempdir()) / "subtitulos_version_info.json"
            _download_file(info_asset["browser_download_url"], info_path, timeout=timeout)
            info = json.loads(info_path.read_text(encoding="utf-8"))
            sha256 = str(info.get("sha256", "")).strip()
            try:
                info_path.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    if not sha256 and sha_asset:
        try:
            sha_path = Path(tempfile.gettempdir()) / "subtitulos_update.sha256"
            _download_file(sha_asset["browser_download_url"], sha_path, timeout=timeout)
            content = sha_path.read_text(encoding="utf-8").strip()
            sha256 = content.split()[0] if content else ""
            try:
                sha_path.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    return {
        "version": tag.lstrip("vV"),
        "zip_url": zip_asset.get("browser_download_url", ""),
        "sha256": sha256.lower(),
        "notes": str(release.get("body", "") or ""),
        "html_url": str(release.get("html_url", "") or ""),
        "size": int(zip_asset.get("size", 0) or 0),
    }


def download_update(update: dict, dest_zip: Path, timeout: int = 120, progress_cb=None) -> Path:
    url = update.get("zip_url", "")
    if not url:
        raise RuntimeError("La actualización no tiene URL de descarga.")
    log.info("Descargando actualización desde %s", url)
    _download_file(url, dest_zip, timeout=timeout, progress_cb=progress_cb)

    expected = str(update.get("sha256", "")).strip().lower()
    if expected:
        actual = _sha256(dest_zip)
        if actual.lower() != expected:
            try:
                dest_zip.unlink(missing_ok=True)
            except Exception:
                pass
            log.error("Verificación SHA256 fallida")
            raise RuntimeError(
                "El archivo descargado no pasó la verificación de integridad (SHA256)."
            )
    return dest_zip


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def apply_update(zip_path: Path) -> None:
    """Extrae el update y lanza un script auxiliar para reemplazar archivos.

    El zip debe tener la estructura de la app (subtitulos.exe, _internal/...).
    No debe incluir `models/` para evitar re-descargar el modelo.
    """
    log.info("Aplicando actualización desde %s", zip_path)
    app_dir = _app_dir()
    staging = Path(tempfile.mkdtemp(prefix="subtitulos-update-"))
    extract_dir = staging / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # Si el zip contiene una sola carpeta raíz, usarla.
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        extract_dir = entries[0]

    if not getattr(sys, "frozen", False):
        # En modo desarrollo, solo extraer a una carpeta y avisar.
        target = app_dir / "_update_extracted"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(extract_dir, target)
        log.info("Modo desarrollo: extraído a %s", target)
        return

    exe_path = Path(sys.executable).resolve()
    pid = os.getpid()
    script = staging / "apply_update.cmd"
    # Robocopy: /E copia subdirs, /R:1 /W:1 reintentos rápidos.
    # Excluir models para no tocar el modelo de IA.
    script_content = f"""@echo off
setlocal
set "SRC={extract_dir}"
set "DST={app_dir}"
set "EXE={exe_path}"
set "PID={pid}"
set "ZIP={zip_path}"
set "STAGING={staging}"

:waitloop
tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
if "%ERRORLEVEL%"=="0" (
  timeout /t 1 /nobreak >NUL
  goto waitloop
)

robocopy "%SRC%" "%DST%" /E /R:2 /W:1 /XD models >NUL
del /f /q "%ZIP%" >NUL 2>&1
rmdir /s /q "%STAGING%" >NUL 2>&1
start "" "%EXE%"
"""
    script.write_text(script_content, encoding="utf-8")

    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )