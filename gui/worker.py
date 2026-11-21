"""Hilo de trabajo para la transcripción (no bloquea la interfaz)."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from core.audio import extract_audio_for_transcription
from core.subtitles import build_cues, words_from_segments
from core.transcriber import Transcriber


class TranscribeWorker(QThread):
    """Ejecuta extracción + transcripción + agrupado en un hilo aparte."""

    progress = Signal(str)
    finished_ok = Signal(list, str, dict)   # (cues, audio_path, info)
    failed = Signal(str)

    def __init__(
        self,
        input_path: str,
        *,
        model: str,
        language: str,
        device: str,
        max_words: int,
        max_chars: int,
        max_gap: float,
        min_duration: float,
        max_duration: float,
        max_lines: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.input_path = input_path
        self.model = model
        self.language = language
        self.device = device
        self.max_words = max_words
        self.max_chars = max_chars
        self.max_gap = max_gap
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.max_lines = max_lines

    def run(self) -> None:
        audio_path = None
        try:
            self.progress.emit("Extrayendo audio...")
            audio_path = extract_audio_for_transcription(self.input_path)

            self.progress.emit(f"Cargando modelo '{self.model}' ({self.device})...")
            transcriber = Transcriber(model_size=self.model, device=self.device)

            self.progress.emit("Transcribiendo...")
            language = None if self.language in ("", "auto") else self.language
            segments, info = transcriber.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
                vad_filter=True,
            )

            words = [w for seg in segments for w in seg.words]
            if not words:
                words = words_from_segments(segments)

            cues = build_cues(
                words,
                max_words=self.max_words,
                max_chars=self.max_chars,
                max_gap=self.max_gap,
                min_duration=self.min_duration,
                max_duration=self.max_duration,
                max_lines=self.max_lines,
            )

            # Incluir palabras para permitir ajustes en la revisión.
            info["words"] = words
            info["max_words"] = self.max_words
            info["max_lines"] = self.max_lines

            # Se conserva el WAV para el waveform; lo limpia la ventana al cerrar.
            self.finished_ok.emit(cues, str(audio_path), info)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.failed.emit(str(exc))
