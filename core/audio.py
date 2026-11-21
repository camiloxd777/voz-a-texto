"""Extracción de audio desde archivos de video/audio usando ffmpeg.

Solo se usa para crear una copia temporal en 16 kHz mono que es lo que el
modelo Whisper necesita internamente.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg


def get_ffmpeg_exe() -> str:
    """Devuelve la ruta al binario de ffmpeg.

    - En ejecutable (PyInstaller): busca el ffmpeg empaquetado junto al .exe.
    - En entorno normal: usa el binario de imageio-ffmpeg.
    """
    if getattr(sys, "frozen", False):
        bases = []
        if hasattr(sys, "_MEIPASS"):
            bases.append(sys._MEIPASS)
        bases.append(os.path.dirname(sys.executable))
        for base in bases:
            for pattern in ("ffmpeg*.exe", "ffmpeg*"):
                for match in glob.glob(os.path.join(base, pattern)):
                    if os.path.isfile(match):
                        return match
        raise RuntimeError(
            "No se encontró el binario de ffmpeg junto al ejecutable."
        )
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio_for_transcription(
    input_path: str | Path,
    work_dir: str | Path | None = None,
) -> Path:
    """Extrae el audio de `input_path` a un WAV temporal de 16 kHz mono.

    Devuelve la ruta del WAV generado (en el directorio temporal del sistema
    o en `work_dir` si se indica). El llamador es responsable de borrarlo.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {input_path}")

    out_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / (input_path.stem + "_16k.wav")

    cmd = [
        get_ffmpeg_exe(),
        "-y",                      # sobrescribir si existe
        "-i", str(input_path),
        "-vn",                     # sin video
        "-ac", "1",                # mono
        "-ar", "16000",            # 16 kHz (lo que espera Whisper)
        "-c:a", "pcm_s16le",       # WAV PCM 16 bits
        "-f", "wav",
        str(out_path),
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al extraer el audio:\n{proc.stderr[-2000:]}"
        )
    if not out_path.exists():
        raise RuntimeError("ffmpeg no generó el archivo de audio esperado.")

    return out_path
