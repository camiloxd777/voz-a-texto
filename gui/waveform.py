"""Widget de forma de onda con regiones de subtítulo y cabeza de reproducción."""

from __future__ import annotations

import wave

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .timeutil import fmt_time


class WaveformWidget(QWidget):
    """Dibuja la onda del audio, resalta los subtítulos y permite hacer clic
    para moverse en el tiempo (seek)."""

    seekRequested = Signal(float)  # segundos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: np.ndarray | None = None
        self._sample_rate = 16000
        self._duration = 0.0
        self._envelope: np.ndarray | None = None
        self._cues: list = []
        self._playhead = 0.0
        self._highlight_index = -1

        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------
    def set_audio(self, path: str | None) -> None:
        if not path:
            self._samples = None
            self._envelope = None
            self._duration = 0.0
            self._playhead = 0.0
            self.update()
            return
        samples, rate = _load_wav(path)
        self._samples = samples
        self._sample_rate = rate
        self._duration = len(samples) / rate if rate else 0.0
        self._envelope = _envelope(samples, buckets=2400)
        self.update()

    def set_cues(self, cues: list) -> None:
        self._cues = cues
        self.update()

    def set_playhead(self, seconds: float) -> None:
        self._playhead = max(0.0, seconds)
        self.update()

    def set_highlight(self, index: int) -> None:
        self._highlight_index = index
        self.update()

    def duration(self) -> float:
        return self._duration

    # ------------------------------------------------------------------
    # Pintado
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        w = self.width()
        h = self.height()
        ruler_h = 22
        wave_top = ruler_h
        wave_h = h - ruler_h

        # Región útil
        margin = 4
        plot_w = w - margin * 2
        if plot_w <= 0:
            return

        # Regiones de subtítulo
        if self._cues and self._duration > 0:
            for i, cue in enumerate(self._cues):
                x0 = margin + int(cue.start / self._duration * plot_w)
                x1 = margin + int(cue.end / self._duration * plot_w)
                if x1 <= x0:
                    x1 = x0 + 1
                if i == self._highlight_index:
                    color = QColor(255, 200, 60, 90)
                else:
                    color = QColor(80, 160, 255, 45)
                painter.fillRect(x0, wave_top, x1 - x0, wave_h, color)

        # Onda
        if self._envelope is not None and len(self._envelope) > 0:
            n = len(self._envelope)
            step = plot_w / n
            center = wave_top + wave_h / 2
            amp = wave_h * 0.42
            pen = QPen(QColor("#3ddc84"))
            pen.setWidth(1)
            painter.setPen(pen)
            for i, v in enumerate(self._envelope):
                x = margin + int(i * step)
                half = max(1, int(v * amp))
                painter.drawLine(x, int(center - half), x, int(center + half))

        # Cabeza de reproducción
        if self._duration > 0:
            px = margin + int(self._playhead / self._duration * plot_w)
            pen = QPen(QColor("#ff5252"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(px, wave_top, px, h - 1)

        # Regla de tiempo
        painter.setPen(QColor("#aaaaaa"))
        if self._duration > 0:
            ticks = 6
            for i in range(ticks + 1):
                t = self._duration * i / ticks
                x = margin + int(t / self._duration * plot_w)
                painter.drawLine(x, ruler_h - 6, x, ruler_h)
                painter.drawText(x + 3, ruler_h - 8, fmt_time(t))
        else:
            painter.drawText(8, ruler_h - 8, "Sin audio")

    # ------------------------------------------------------------------
    # Interacción
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._duration <= 0:
            return
        margin = 4
        plot_w = self.width() - margin * 2
        if plot_w <= 0:
            return
        x = event.position().x() - margin
        frac = max(0.0, min(1.0, x / plot_w))
        self.seekRequested.emit(frac * self._duration)


def _load_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        sampwidth = w.getsampwidth()
        rate = w.getframerate()
        n = w.getnframes()
        data = w.readframes(n)

    if sampwidth == 2:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        samples = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0

    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)

    return samples, rate


def _envelope(samples: np.ndarray, buckets: int = 2400) -> np.ndarray:
    n = len(samples)
    if n == 0:
        return np.zeros(buckets, dtype=np.float32)
    per = max(1, n // buckets)
    trimmed = samples[: per * buckets]
    trimmed = trimmed.reshape(buckets, per)
    return np.abs(trimmed).max(axis=1).astype(np.float32)
