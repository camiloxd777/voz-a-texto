"""Ventana simple: selecciona audio, elige formato, transcribe y te da el archivo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.exporters import to_ass, to_sbv, to_srt, to_ttml, to_vegas_csv

from .worker import TranscribeWorker

# Ajustes fijos del flujo simple.
FPS = 60.0          # frame rate de tu proyecto de Vegas
LANGUAGE = "auto"   # detecta el idioma solo (español, inglés, etc.)
MODEL = "large-v3"  # el modelo más preciso de Whisper open-source
DEVICE = "auto"     # usa GPU si hay, si no CPU
MAX_CHARS = 45      # tope de seguridad (el selector de palabras manda)
MAX_GAP = 0.4
MIN_DURATION = 0.3
MAX_DURATION = 4.0

# Opciones de palabras por subtítulo: (max_words, max_lines, etiqueta).
WORD_OPTIONS = [
    (1, 1, "1 palabra"),
    (2, 1, "2 palabras"),
    (3, 1, "3 palabras"),
    (4, 1, "4 palabras"),
    (5, 1, "5 palabras"),
    (3, 2, "3 palabras en 2 líneas"),
    (4, 2, "4 palabras en 2 líneas"),
    (5, 2, "5 palabras en 2 líneas"),
]

# Formatos disponibles (key, extensión, etiqueta, descripción).
FORMATS = [
    {
        "key": "csv",
        "ext": ".vegas.csv",
        "label": "CSV — Vegas",
        "desc": "Para Sony Vegas: Insert > Insert Subtitles from File.",
    },
    {
        "key": "srt",
        "ext": ".srt",
        "label": "SRT — Premiere / CapCut / DaVinci",
        "desc": "El formato universal: funciona en casi todo (Premiere, CapCut, DaVinci, YouTube...).",
    },
    {
        "key": "sbv",
        "ext": ".sbv",
        "label": "SBV — YouTube",
        "desc": "Formato de subtítulos de YouTube (SubViewer).",
    },
    {
        "key": "ass",
        "ext": ".ass",
        "label": "ASS — Anime / diseño",
        "desc": "Subtítulos con estilo avanzado: fuentes, colores y posiciones (anime, fansubs).",
    },
    {
        "key": "ttml",
        "ext": ".ttml",
        "label": "TTML — Broadcast / streaming",
        "desc": "XML profesional para TV y plataformas de streaming (Netflix, DASH).",
    },
]


class SimpleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtítulos automáticos")
        self.resize(600, 520)

        self._input_path: str | None = None
        self._worker: TranscribeWorker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(10)

        title = QLabel("Subtítulos automáticos")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("Sube tu audio y genera subtítulos en el formato que elijas")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888;")
        root.addWidget(subtitle)

        root.addSpacing(4)

        self.open_btn = QPushButton("📁  Seleccionar audio / video")
        self.open_btn.setMinimumHeight(44)
        self.open_btn.clicked.connect(self._open_file)
        root.addWidget(self.open_btn)

        self.file_label = QLabel("")
        self.file_label.setAlignment(Qt.AlignCenter)
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: #bbb;")
        root.addWidget(self.file_label)

        # Palabras por línea
        words_row = QHBoxLayout()
        words_label = QLabel("Palabras por línea:")
        words_label.setStyleSheet("color: #ddd;")
        words_row.addWidget(words_label)
        self.words_combo = QComboBox()
        self.words_combo.addItems([opt[2] for opt in WORD_OPTIONS])
        self.words_combo.setCurrentIndex(2)  # 3 palabras por defecto
        words_row.addWidget(self.words_combo, 1)
        root.addLayout(words_row)

        # Formato de salida
        fmt_row = QHBoxLayout()
        fmt_label = QLabel("Formato:")
        fmt_label.setStyleSheet("color: #ddd;")
        fmt_row.addWidget(fmt_label)
        self.format_combo = QComboBox()
        for fmt in FORMATS:
            self.format_combo.addItem(fmt["label"])
        self.format_combo.setCurrentIndex(1)  # SRT por defecto
        self.format_combo.currentIndexChanged.connect(self._update_format_desc)
        fmt_row.addWidget(self.format_combo, 1)
        root.addLayout(fmt_row)

        # Mini leyenda (descripción del formato seleccionado)
        self.format_desc = QLabel("")
        self.format_desc.setWordWrap(True)
        self.format_desc.setStyleSheet("color: #999; font-size: 11px;")
        root.addWidget(self.format_desc)
        self._update_format_desc()

        self.transcribe_btn = QPushButton("🎙️  Transcribir")
        self.transcribe_btn.setMinimumHeight(44)
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.clicked.connect(self._transcribe)
        root.addWidget(self.transcribe_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #5bd3ff;")
        root.addWidget(self.status_label)

        # Resultado (oculto hasta terminar)
        self.result_frame = QFrame()
        self.result_frame.setFrameShape(QFrame.StyledPanel)
        self.result_frame.setVisible(False)
        result_layout = QVBoxLayout(self.result_frame)

        self.done_label = QLabel("✅  ¡Listo! Tu archivo:")
        self.done_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        result_layout.addWidget(self.done_label)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        result_layout.addWidget(self.path_edit)

        buttons = QHBoxLayout()
        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.clicked.connect(self._open_folder)
        buttons.addWidget(self.open_folder_btn)

        self.copy_btn = QPushButton("Copiar ruta")
        self.copy_btn.clicked.connect(self._copy_path)
        buttons.addWidget(self.copy_btn)

        result_layout.addLayout(buttons)
        root.addWidget(self.result_frame)

        root.addStretch(1)

        credit = QLabel("creado por masku")
        credit.setAlignment(Qt.AlignCenter)
        credit.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(credit)

    # ------------------------------------------------------------------
    def _update_format_desc(self) -> None:
        idx = self.format_combo.currentIndex()
        if 0 <= idx < len(FORMATS):
            self.format_desc.setText(FORMATS[idx]["desc"])

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona un audio o video",
            "",
            "Medios (*.mp4 *.mkv *.mov *.avi *.mp3 *.wav *.m4a *.flac *.aac *.ogg);;Todos (*.*)",
        )
        if not path:
            return
        self._input_path = path
        self.file_label.setText(Path(path).name)
        self.transcribe_btn.setEnabled(True)
        self.result_frame.setVisible(False)

    def _transcribe(self) -> None:
        if not self._input_path:
            return

        opt = WORD_OPTIONS[self.words_combo.currentIndex()]
        max_words, max_lines = opt[0], opt[1]

        self._worker = TranscribeWorker(
            self._input_path,
            model=MODEL,
            language=LANGUAGE,
            device=DEVICE,
            max_words=max_words,
            max_chars=MAX_CHARS,
            max_gap=MAX_GAP,
            min_duration=MIN_DURATION,
            max_duration=MAX_DURATION,
            max_lines=max_lines,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self.transcribe_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Preparando...")
        self.result_frame.setVisible(False)
        self._worker.start()

    def _on_progress(self, msg: str) -> None:
        self.status_label.setText(msg)

    def _on_finished(self, cues: list, audio_path: str, info: dict) -> None:
        self.progress.setVisible(False)
        self.transcribe_btn.setEnabled(True)
        self.open_btn.setEnabled(True)

        if not cues:
            self.status_label.setText("No se detectó voz en el audio.")
            return

        fmt = FORMATS[self.format_combo.currentIndex()]
        out_path = Path(self._input_path).with_suffix(fmt["ext"])

        key = fmt["key"]
        if key == "csv":
            out_path.write_text(to_vegas_csv(cues, fps=FPS), encoding="utf-8")
        elif key == "srt":
            out_path.write_text(to_srt(cues), encoding="utf-8")
        elif key == "sbv":
            out_path.write_text(to_sbv(cues), encoding="utf-8")
        elif key == "ass":
            out_path.write_text(to_ass(cues), encoding="utf-8")
        elif key == "ttml":
            out_path.write_text(to_ttml(cues), encoding="utf-8")

        self.status_label.setText(f"Listo: {len(cues)} subtítulos.")
        self.done_label.setText(f"✅  ¡Listo! Tu archivo ({fmt['label']}):")
        self.path_edit.setText(str(out_path))
        self.result_frame.setVisible(True)

    def _on_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.transcribe_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.status_label.setText("")
        self.result_frame.setVisible(False)
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self, "Error", msg)

    def _open_folder(self) -> None:
        path = self.path_edit.text().strip()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _copy_path(self) -> None:
        QApplication.clipboard().setText(self.path_edit.text().strip())
        self.copy_btn.setText("¡Copiada!")
