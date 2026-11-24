"""Hilo de trabajo para la transcripción (no bloquea la interfaz)."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from core.audio import extract_audio_for_transcription
from core.logging_setup import get_logger
from core.subtitles import build_cues, words_from_segments
from core.transcriber import Transcriber
from core.translator import translate_texts


class TranscribeWorker(QThread):
    """Ejecuta extracción + transcripción + agrupado en un hilo aparte."""

    progress = Signal(str)
    progress_pct = Signal(int)  # 0..100 durante la transcripción
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
        target_language: str = "original",
        beam_size: int = 8,
        best_of: int = 8,
        temperature=None,
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
        self.target_language = target_language
        self.beam_size = beam_size
        self.best_of = best_of
        self.temperature = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] if temperature is None else temperature
        self.log = get_logger("worker")

    def run(self) -> None:
        audio_path = None
        try:
            self.log.info("Inicio: %s (modelo=%s, device=%s, target=%s)",
                          self.input_path, self.model, self.device, self.target_language)
            self.progress.emit("Extrayendo audio...")
            audio_path = extract_audio_for_transcription(self.input_path)
            self.log.info("Audio extraído: %s", audio_path)

            self.progress.emit(f"Cargando modelo '{self.model}'...")
            transcriber = Transcriber(model_size=self.model, device=self.device)
            dev_label = "GPU (CUDA)" if transcriber.device == "cuda" else "CPU"
            self.log.info("Modelo cargado en %s (compute=%s)", transcriber.device, transcriber.compute_type)
            self.progress.emit(f"Modelo listo · usando {dev_label}")

            self.progress.emit("Transcribiendo...")
            language = None if self.language in ("", "auto") else self.language
            target = self.target_language or "original"
            task = "transcribe" if target == "original" else "translate"

            def on_seg(current: float, total: float) -> None:
                if total > 0:
                    self.progress_pct.emit(int(min(100.0, current * 100.0 / total)))

            segments, info = transcriber.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
                vad_filter=True,
                task=task,
                beam_size=self.beam_size,
                best_of=self.best_of,
                temperature=self.temperature,
                progress_cb=on_seg,
            )
            self.log.info("Transcripción lista: %d segmentos, idioma=%s", len(segments), info.get("language"))

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

            # Traducir post-procesado si el destino no es original ni inglés.
            if target not in ("original", "en") and cues:
                self.progress.emit("Traduciendo...")
                texts = [c.text for c in cues]
                translated = translate_texts(texts, target)
                for c, t in zip(cues, translated):
                    c.text = t
                self.log.info("Traducción aplicada a %s", target)

            # Incluir palabras para permitir ajustes en la revisión.
            info["words"] = words
            info["max_words"] = self.max_words
            info["max_lines"] = self.max_lines
            info["target_language"] = target
            info["device"] = transcriber.device

            # Se conserva el WAV para el waveform; lo limpia la ventana al cerrar.
            self.finished_ok.emit(cues, str(audio_path), info)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Error en la transcripción")
            self.failed.emit(str(exc))
