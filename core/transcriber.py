"""Motor de transcripción basado en faster-whisper (Whisper local).

Usa GPU CUDA cuando está disponible (float16) y devuelve tanto segmentos
como palabras con marcas de tiempo, necesarias para generar subtítulos
estilo Premiere.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _register_nvidia_dll_paths() -> None:
    """Añade los directorios con las DLLs de CUDA (cuBLAS) al PATH.

    ctranslate2 carga cuBLAS (cublas64_12.dll) con LoadLibrary, que busca en el
    PATH del proceso (pero NO en os.add_dll_directory). Registramos ambos por
    si acaso. Necesario cuando CUDA 12 se instala vía pip (nvidia-cublas-cu12)
    sin tener el CUDA Toolkit del sistema.

    Funciona tanto en entorno normal como empaquetado con PyInstaller.
    """
    if os.name != "nt":
        return

    roots: list[str] = []

    # Empaquetado (PyInstaller): las DLLs van junto al .exe o en _MEIPASS.
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        roots.append(os.path.join(base, "nvidia"))
        roots.append(base)

    # Entorno normal (pip): site-packages/nvidia.
    try:
        roots.append(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia"))
    except Exception:
        pass

    dirs: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        # Subcarpetas */bin (estructura de los wheels nvidia-*).
        try:
            for sub in os.listdir(root):
                bin_dir = os.path.join(root, sub, "bin")
                if os.path.isdir(bin_dir) and any(
                    f.endswith(".dll") for f in os.listdir(bin_dir)
                ):
                    dirs.append(bin_dir)
        except OSError:
            pass
        # También el propio directorio si contiene DLLs sueltas.
        try:
            if any(f.endswith(".dll") for f in os.listdir(root)):
                dirs.append(root)
        except OSError:
            pass

    dirs = [d for d in dirs if d not in seen and not seen.add(d)]
    if not dirs:
        return

    path = os.environ.get("PATH", "")
    new_path = os.pathsep.join(dirs) + (os.pathsep + path if path else "")
    os.environ["PATH"] = new_path
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass


_register_nvidia_dll_paths()


def _resolve_model_path(model_size: str) -> str:
    """Si el modelo viene incluido con la app, devuelve su ruta local.

    Así el instalador puede incluir el modelo de IA (~3 GB) y la app lo usa
    sin descargar nada ni necesitar internet. Si no se encuentra, devuelve el
    nombre original (faster-whisper lo descargará de Hugging Face como antes).
    """
    # Si ya es una ruta a un directorio con el modelo, úsala tal cual.
    try:
        p = Path(model_size)
        if p.is_dir() and (p / "model.bin").exists():
            return str(p)
    except Exception:
        pass

    names = [model_size, f"faster-whisper-{model_size}"]
    candidates: list[Path] = []

    # Empaquetado (PyInstaller): junto al .exe y en _MEIPASS/_internal.
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        for base in (exe_dir, meipass):
            for name in names:
                candidates.append(base / "models" / name)
                candidates.append(base / name)

    # Desarrollo: carpeta models/ del proyecto.
    project_root = Path(__file__).resolve().parent.parent
    for name in names:
        candidates.append(project_root / "models" / name)

    for c in candidates:
        try:
            if c.is_dir() and (c / "model.bin").exists():
                return str(c)
        except Exception:
            continue

    return model_size


@dataclass
class Word:
    """Palabra individual con marcas de tiempo (en segundos)."""

    start: float
    end: float
    text: str


@dataclass
class Segment:
    """Segmento (frase) transcrito con marcas de tiempo (en segundos)."""

    start: float
    end: float
    text: str
    words: list[Word]


class Transcriber:
    """Envuelve faster-whisper para transcribir un archivo de audio."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        # Import diferido para que el resto del módulo sea ligero y para
        # dar un mensaje de error claro si no está instalado faster-whisper.
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "faster-whisper no está instalado. Ejecuta: pip install -r requirements.txt"
            ) from exc

        if device == "auto":
            device = "cuda" if self._cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        resolved = _resolve_model_path(model_size)

        self.model_size = model_size
        self.model_path = resolved
        self.device = device
        self.compute_type = compute_type

        self._model = WhisperModel(
            resolved,
            device=device,
            compute_type=compute_type,
        )

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    @property
    def model(self):
        return self._model

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = "es",
        word_timestamps: bool = True,
        vad_filter: bool = True,
        task: str = "transcribe",
        beam_size: int = 8,
        best_of: int = 8,
        temperature: float | list[float] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    ) -> tuple[list[Segment], dict]:
        """Transcribe `audio_path` y devuelve (segmentos, info).

        `task`: "transcribe" (idioma original) o "translate" (traducir a inglés).
        `info` contiene language, language_probability, duration, etc.
        """
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            task=task,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            beam_size=beam_size,
            best_of=best_of,
            temperature=list(temperature) if isinstance(temperature, (list, tuple)) else temperature,
            condition_on_previous_text=True,
        )

        segments: list[Segment] = []
        for seg in segments_iter:
            words = [
                Word(start=w.start, end=w.end, text=w.word.strip())
                for w in (seg.words or [])
                if w.word.strip()
            ]
            segments.append(
                Segment(
                    start=float(seg.start),
                    end=float(seg.end),
                    text=seg.text.strip(),
                    words=words,
                )
            )

        return segments, {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "duration_after_vad": info.duration_after_vad,
        }
