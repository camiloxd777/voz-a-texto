# -*- mode: python ; coding: utf-8 -*-
"""Especificación de PyInstaller para generar el ejecutable (onedir).

Genera la carpeta `dist/subtitulos/` con `subtitulos.exe` dentro.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# Datos/binarios/imports de faster_whisper (incluye el modelo VAD silero_vad.onnx)
fw_datas, fw_binaries, fw_hidden = collect_all("faster_whisper")

venv_site = Path(r"D:\subtitulos\.venv\Lib\site-packages")

# DLLs de CUDA (cuBLAS + runtime) necesarias para usar la GPU.
# Se colocan en la subcarpeta "nvidia" del bundle y transcriber.py las
# registra en el PATH al arrancar.
cuda_files = [
    venv_site / "nvidia" / "cublas" / "bin" / "cublas64_12.dll",
    venv_site / "nvidia" / "cublas" / "bin" / "cublasLt64_12.dll",
    venv_site / "nvidia" / "cuda_runtime" / "bin" / "cudart64_12.dll",
]
cuda_binaries = [(str(p), "nvidia") for p in cuda_files if p.exists()]

# Binario de ffmpeg (imageio-ffmpeg) en la raíz del bundle.
ffmpeg_dir = venv_site / "imageio_ffmpeg" / "binaries"
ffmpeg_exe = next(ffmpeg_dir.glob("ffmpeg*.exe"), None)
ffmpeg_binaries = [(str(ffmpeg_exe), ".")] if ffmpeg_exe else []

# Icono de la app.
icon_file = Path(r"D:\subtitulos\assets\app_icon.ico")

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=fw_binaries + cuda_binaries + ffmpeg_binaries,
    datas=fw_datas + ([(str(icon_file), ".")] if icon_file.exists() else []),
    hiddenimports=fw_hidden + ["ctranslate2", "imageio_ffmpeg", "av"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="subtitulos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # sin UPX: evita problemas con DLLs grandes
    console=False,      # app de ventana (sin consola negra)
    icon=str(icon_file) if icon_file.exists() else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="subtitulos",
)
