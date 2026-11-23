"""Ventana simple: selecciona audio, elige formato, transcribe y te da el archivo."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
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
from core.translator import TARGET_LANGUAGES, download_language, is_language_installed
from core.updater import apply_update, check_for_update, download_update
from core.version import APP_VERSION

from .review_dialog import ReviewDialog
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

# Opciones de traducción (key, etiqueta).
TRANSLATE_OPTIONS = [
    ("original", "Mantener original"),
    ("en", "Inglés"),
    ("ja", "Japonés"),
    ("zh", "Chino"),
    ("fr", "Francés"),
    ("pt", "Portugués"),
    ("ko", "Coreano"),
]

# Opciones de calidad/velocidad (key, etiqueta, beam, best_of, temperature, desc)
QUALITY_OPTIONS = [
    (
        "fast",
        "Rápido",
        1,
        1,
        [0.0],
        "Más veloz; puede fallar un poco en audio difícil.",
    ),
    (
        "balanced",
        "Equilibrado",
        5,
        5,
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "Buen balance entre velocidad y precisión.",
    ),
    (
        "max",
        "Máxima calidad",
        8,
        8,
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "Más preciso, pero más lento (recomendado si el audio es difícil).",
    ),
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


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "SubtitulosAutomaticos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_config() -> dict:
    p = _config_dir() / "config.json"
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_config(cfg: dict) -> None:
    p = _config_dir() / "config.json"
    try:
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


THEMES = {
    "dark": {
        "name": "Oscuro",
        "bg": "#1e1e1e",
        "fg": "#ddd",
        "muted": "#888",
        "muted2": "#999",
        "accent": "#5bd3ff",
        "panel": "#2a2a2a",
        "border": "#3a3a3a",
        "btn_bg": "#333",
        "btn_fg": "#ddd",
        "input_bg": "#2b2b2b",
        "input_fg": "#eee",
    },
    "light": {
        "name": "Claro",
        "bg": "#f5f5f5",
        "fg": "#222",
        "muted": "#555",
        "muted2": "#666",
        "accent": "#0078d4",
        "panel": "#ffffff",
        "border": "#ccc",
        "btn_bg": "#e8e8e8",
        "btn_fg": "#222",
        "input_bg": "#ffffff",
        "input_fg": "#222",
    },
}


def _build_qss(theme: dict) -> str:
    return f"""
    QWidget {{ background: {theme['bg']}; color: {theme['fg']}; }}
    QLabel {{ background: transparent; }}
    QLineEdit, QComboBox {{
        background: {theme['input_bg']}; color: {theme['input_fg']};
        border: 1px solid {theme['border']}; border-radius: 4px; padding: 4px 6px;
    }}
    QComboBox::drop-down {{ border: none; }}
    QPushButton {{
        background: {theme['btn_bg']}; color: {theme['btn_fg']};
        border: 1px solid {theme['border']}; border-radius: 4px; padding: 6px 10px;
    }}
    QPushButton:hover {{ border-color: {theme['accent']}; }}
    QPushButton:disabled {{ color: {theme['muted2']}; }}
    QProgressBar {{
        border: 1px solid {theme['border']}; border-radius: 4px;
        background: {theme['panel']}; text-align: center;
    }}
    QProgressBar::chunk {{ background: {theme['accent']}; border-radius: 4px; }}
    QFrame {{ background: {theme['panel']}; }}
    """


class UpdateCheckWorker(QThread):
    update_available = Signal(dict)
    up_to_date = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            info = check_for_update(timeout=10)
            if info:
                self.update_available.emit(info)
            else:
                self.up_to_date.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = Signal(str)
    progress_bytes = Signal(int, int)  # downloaded, total
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info

    def run(self) -> None:
        try:
            import tempfile
            from pathlib import Path

            self.progress.emit("Descargando actualización...")
            dest = Path(tempfile.gettempdir()) / "subtitulos-app-update.zip"
            download_update(
                self.update_info,
                dest,
                timeout=300,
                progress_cb=lambda d, t: self.progress_bytes.emit(d, t),
            )
            self.progress.emit("Aplicando actualización...")
            self.progress_bytes.emit(0, 0)  # indeterminado
            apply_update(dest)
            self.finished_ok.emit(str(dest))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class LanguageDownloadWorker(QThread):
    progress = Signal(int, int)  # downloaded, total
    finished_ok = Signal(str)    # lang code
    failed = Signal(str)

    def __init__(self, lang_code: str, parent=None):
        super().__init__(parent)
        self.lang_code = lang_code

    def run(self) -> None:
        try:
            download_language(
                self.lang_code,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            self.finished_ok.emit(self.lang_code)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SimpleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtítulos automáticos")
        self.resize(600, 560)

        self._input_path: str | None = None
        self._worker: TranscribeWorker | None = None
        self._update_info: dict | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_dl_worker: UpdateDownloadWorker | None = None
        self._manual_update_check = False
        self._lang_dl_worker: LanguageDownloadWorker | None = None
        self._pending_transcribe: dict | None = None
        self._config = _load_config()
        self._theme_name = self._config.get("theme", "dark")
        if self._theme_name not in THEMES:
            self._theme_name = "dark"

        self._build_ui()
        self._apply_theme()
        self._start_update_check()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(10)

        # Banner de actualización (oculto por defecto)
        self.update_frame = QFrame()
        self.update_frame.setVisible(False)
        self.update_frame.setStyleSheet(
            "QFrame { background: #1f3a2b; border: 1px solid #2f6b45; border-radius: 6px; }"
            "QLabel { color: #dff5e6; }"
        )
        uf_outer = QVBoxLayout(self.update_frame)
        uf_outer.setContentsMargins(10, 6, 10, 6)
        uf_outer.setSpacing(6)
        uf = QHBoxLayout()
        uf.setContentsMargins(0, 0, 0, 0)
        self.update_label = QLabel("Hay una actualización disponible.")
        self.update_label.setWordWrap(True)
        uf.addWidget(self.update_label, 1)
        self.update_btn = QPushButton("Actualizar")
        self.update_btn.clicked.connect(self._download_and_apply_update)
        uf.addWidget(self.update_btn)
        uf_outer.addLayout(uf)
        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        self.update_progress.setTextVisible(True)
        self.update_progress.setFixedHeight(14)
        uf_outer.addWidget(self.update_progress)
        root.addWidget(self.update_frame)

        title = QLabel("Subtítulos automáticos")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self.subtitle_label = QLabel("Sube tu audio y genera subtítulos en el formato que elijas")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("color: #888;")
        root.addWidget(self.subtitle_label)

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
        self.words_label = QLabel("Palabras por línea:")
        self.words_label.setStyleSheet("color: #ddd;")
        words_row.addWidget(self.words_label)
        self.words_combo = QComboBox()
        self.words_combo.addItems([opt[2] for opt in WORD_OPTIONS])
        self.words_combo.setCurrentIndex(2)  # 3 palabras por defecto
        words_row.addWidget(self.words_combo, 1)
        root.addLayout(words_row)

        # Traducción
        tr_row = QHBoxLayout()
        self.tr_label = QLabel("Traducir:")
        self.tr_label.setStyleSheet("color: #ddd;")
        tr_row.addWidget(self.tr_label)
        self.translate_combo = QComboBox()
        self._refresh_translate_combo()
        self.translate_combo.setCurrentIndex(0)  # Mantener original
        tr_row.addWidget(self.translate_combo, 1)
        root.addLayout(tr_row)

        # Calidad / velocidad
        q_row = QHBoxLayout()
        self.q_label = QLabel("Calidad:")
        self.q_label.setStyleSheet("color: #ddd;")
        q_row.addWidget(self.q_label)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([opt[1] for opt in QUALITY_OPTIONS])
        self.quality_combo.setCurrentIndex(2)  # Máxima calidad por defecto (como antes)
        self.quality_combo.currentIndexChanged.connect(self._update_quality_desc)
        q_row.addWidget(self.quality_combo, 1)
        root.addLayout(q_row)

        self.quality_desc = QLabel("")
        self.quality_desc.setWordWrap(True)
        self.quality_desc.setStyleSheet("color: #999; font-size: 11px;")
        root.addWidget(self.quality_desc)
        self._update_quality_desc()

        # Formato de salida
        fmt_row = QHBoxLayout()
        self.fmt_label = QLabel("Formato:")
        self.fmt_label.setStyleSheet("color: #ddd;")
        fmt_row.addWidget(self.fmt_label)
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

        bottom = QHBoxLayout()
        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setStyleSheet("color: #666; font-size: 11px;")
        bottom.addWidget(self.version_label)

        self.check_updates_btn = QPushButton("Buscar actualizaciones")
        self.check_updates_btn.setFlat(True)
        self.check_updates_btn.setCursor(Qt.PointingHandCursor)
        self.check_updates_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 11px; padding: 2px 6px; }"
            "QPushButton:hover { color: #bbb; }"
            "QPushButton:disabled { color: #555; }"
        )
        self.check_updates_btn.clicked.connect(self._manual_check_updates)
        bottom.addWidget(self.check_updates_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setFlat(True)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setStyleSheet(
            "QPushButton { color: #888; font-size: 11px; padding: 2px 6px; }"
            "QPushButton:hover { color: #bbb; }"
        )
        self.theme_btn.clicked.connect(self._toggle_theme)
        bottom.addWidget(self.theme_btn)

        bottom.addStretch(1)

        self.credit_label = QLabel(
            '<a href="https://linktr.ee/maskuku" style="color:#888; text-decoration:none;">creado por masku</a>'
        )
        self.credit_label.setOpenExternalLinks(True)
        self.credit_label.setStyleSheet("font-size: 11px;")
        bottom.addWidget(self.credit_label)
        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Tema
    def _toggle_theme(self) -> None:
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self._config["theme"] = self._theme_name
        _save_config(self._config)
        self._apply_theme()

    def _apply_theme(self) -> None:
        theme = THEMES[self._theme_name]
        self.setStyleSheet(_build_qss(theme))
        self.theme_btn.setText("Modo claro" if self._theme_name == "dark" else "Modo oscuro")
        # Actualizar estilos inline para que respeten el tema
        muted = theme["muted"]
        muted2 = theme["muted2"]
        fg = theme["fg"]
        accent = theme["accent"]
        for lbl in [getattr(self, n, None) for n in ("subtitle_label", "file_label", "words_label", "tr_label", "q_label", "fmt_label")]:
            if lbl:
                lbl.setStyleSheet(f"color: {muted};")
        for lbl in [getattr(self, n, None) for n in ("quality_desc", "format_desc")]:
            if lbl:
                lbl.setStyleSheet(f"color: {muted2}; font-size: 11px;")
        if hasattr(self, "status_label"):
            self.status_label.setStyleSheet(f"color: {accent};")
        if hasattr(self, "version_label"):
            self.version_label.setStyleSheet(f"color: {muted2}; font-size: 11px;")
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setStyleSheet(
                f"QPushButton {{ color: {muted}; font-size: 11px; padding: 2px 6px; border: none; background: transparent; }}"
                f"QPushButton:hover {{ color: {fg}; }}"
                f"QPushButton:disabled {{ color: {muted2}; }}"
            )
        if hasattr(self, "theme_btn"):
            self.theme_btn.setStyleSheet(
                f"QPushButton {{ color: {muted}; font-size: 11px; padding: 2px 6px; border: none; background: transparent; }}"
                f"QPushButton:hover {{ color: {fg}; }}"
            )
        if hasattr(self, "credit_label"):
            link_color = muted if self._theme_name == "dark" else muted
            self.credit_label.setText(
                f'<a href="https://linktr.ee/maskuku" style="color:{link_color}; text-decoration:none;">creado por masku</a>'
            )
        # Reaplicar estilo del banner de update si está visible
        if hasattr(self, "update_frame") and self.update_frame.isVisible():
            # conservar el estilo actual según el texto del botón/label es complejo;
            # usar estilo neutro de info si no es el de "actualización disponible"
            pass

    def _translate_option_label(self, key: str, label: str) -> str:
        if key in ("original", "en"):
            return label
        return label if is_language_installed(key) else f"{label} (descargar)"

    def _refresh_translate_combo(self) -> None:
        current = self.translate_combo.currentIndex()
        self.translate_combo.blockSignals(True)
        self.translate_combo.clear()
        for key, label in TRANSLATE_OPTIONS:
            self.translate_combo.addItem(self._translate_option_label(key, label))
        if 0 <= current < len(TRANSLATE_OPTIONS):
            self.translate_combo.setCurrentIndex(current)
        self.translate_combo.blockSignals(False)

    def _update_format_desc(self) -> None:
        idx = self.format_combo.currentIndex()
        if 0 <= idx < len(FORMATS):
            self.format_desc.setText(FORMATS[idx]["desc"])

    def _update_quality_desc(self) -> None:
        idx = self.quality_combo.currentIndex()
        if 0 <= idx < len(QUALITY_OPTIONS):
            self.quality_desc.setText(QUALITY_OPTIONS[idx][5])

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
        target_language = TRANSLATE_OPTIONS[self.translate_combo.currentIndex()][0]
        q = QUALITY_OPTIONS[self.quality_combo.currentIndex()]
        _, _, beam_size, best_of, temperature, _ = q

        params = dict(
            max_words=max_words,
            max_lines=max_lines,
            target_language=target_language,
            beam_size=beam_size,
            best_of=best_of,
            temperature=temperature,
        )

        if not is_language_installed(target_language):
            lang_label = dict(TRANSLATE_OPTIONS).get(target_language, target_language)
            from PySide6.QtWidgets import QMessageBox

            r = QMessageBox.question(
                self,
                "Descargar idioma",
                f"El idioma «{lang_label}» necesita descargarse antes de traducir.\n\n¿Descargarlo ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if r != QMessageBox.Yes:
                return
            self._pending_transcribe = params
            self._start_language_download(target_language)
            return

        self._start_transcription(params)

    def _start_language_download(self, lang_code: str) -> None:
        self.transcribe_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText(f"Descargando idioma {lang_code}...")
        self.result_frame.setVisible(False)
        self._lang_dl_worker = LanguageDownloadWorker(lang_code, self)
        self._lang_dl_worker.progress.connect(self._on_lang_dl_progress)
        self._lang_dl_worker.finished_ok.connect(self._on_lang_dl_finished)
        self._lang_dl_worker.failed.connect(self._on_lang_dl_failed)
        self._lang_dl_worker.start()

    def _on_lang_dl_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(downloaded)
            pct = int(downloaded * 100 / total)
            self.status_label.setText(f"Descargando idioma... {pct}% ({downloaded/(1024*1024):.0f}/{total/(1024*1024):.0f} MB)")
        else:
            self.progress.setRange(0, 0)
            self.status_label.setText(f"Descargando idioma... {downloaded/(1024*1024):.0f} MB")

    def _on_lang_dl_finished(self, lang_code: str) -> None:
        self._refresh_translate_combo()
        params = self._pending_transcribe
        self._pending_transcribe = None
        if params:
            self.status_label.setText("Idioma descargado. Iniciando transcripción...")
            self._start_transcription(params)
        else:
            self.progress.setVisible(False)
            self.transcribe_btn.setEnabled(True)
            self.open_btn.setEnabled(True)
            self.status_label.setText("Idioma descargado.")

    def _on_lang_dl_failed(self, msg: str) -> None:
        self._pending_transcribe = None
        self.progress.setVisible(False)
        self.transcribe_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.status_label.setText("")
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self, "Error descargando idioma", msg)

    def _start_transcription(self, params: dict) -> None:
        self._worker = TranscribeWorker(
            self._input_path,
            model=MODEL,
            language=LANGUAGE,
            device=DEVICE,
            max_words=params["max_words"],
            max_chars=MAX_CHARS,
            max_gap=MAX_GAP,
            min_duration=MIN_DURATION,
            max_duration=MAX_DURATION,
            max_lines=params["max_lines"],
            target_language=params["target_language"],
            beam_size=params["beam_size"],
            best_of=params["best_of"],
            temperature=params["temperature"],
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self.transcribe_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
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
            self._cleanup_audio(audio_path)
            return

        # Revisión antes de generar el archivo.
        self.status_label.setText(f"Transcripción lista: {len(cues)} subtítulos. Revisa antes de generar.")
        dialog = ReviewDialog(cues, info, self)
        accepted = dialog.exec()
        self._cleanup_audio(audio_path)

        if not accepted:
            self.status_label.setText("Revisión cancelada. No se generó ningún archivo.")
            return

        final_cues = dialog.result_cues()
        if not final_cues:
            self.status_label.setText("No hay subtítulos para exportar.")
            return

        fmt = FORMATS[self.format_combo.currentIndex()]
        out_path = Path(self._input_path).with_suffix(fmt["ext"])

        key = fmt["key"]
        if key == "csv":
            out_path.write_text(to_vegas_csv(final_cues, fps=FPS), encoding="utf-8")
        elif key == "srt":
            out_path.write_text(to_srt(final_cues), encoding="utf-8")
        elif key == "sbv":
            out_path.write_text(to_sbv(final_cues), encoding="utf-8")
        elif key == "ass":
            out_path.write_text(to_ass(final_cues), encoding="utf-8")
        elif key == "ttml":
            out_path.write_text(to_ttml(final_cues), encoding="utf-8")

        self.status_label.setText(f"Listo: {len(final_cues)} subtítulos.")
        self.done_label.setText(f"✅  ¡Listo! Tu archivo ({fmt['label']}):")
        self.path_edit.setText(str(out_path))
        self.result_frame.setVisible(True)

    @staticmethod
    def _cleanup_audio(audio_path: str | None) -> None:
        if not audio_path:
            return
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

    def _on_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.transcribe_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.status_label.setText("")
        self.result_frame.setVisible(False)
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self, "Error", msg)

    # ------------------------------------------------------------------
    # Actualizaciones
    def _start_update_check(self, manual: bool = False) -> None:
        self._manual_update_check = manual
        if manual and hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(False)
            self.check_updates_btn.setText("Buscando...")
        self._update_check_worker = UpdateCheckWorker(self)
        self._update_check_worker.update_available.connect(self._on_update_available)
        self._update_check_worker.up_to_date.connect(self._on_update_up_to_date)
        self._update_check_worker.failed.connect(self._on_update_check_failed)
        self._update_check_worker.start()

    def _manual_check_updates(self) -> None:
        self._start_update_check(manual=True)

    def _restore_check_updates_btn(self) -> None:
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(True)
            self.check_updates_btn.setText("Buscar actualizaciones")

    def _on_update_available(self, info: dict) -> None:
        self._update_info = info
        version = info.get("version", "?")
        self.update_label.setText(f"Actualización disponible: v{version} (actual: v{APP_VERSION})")
        self.update_btn.setVisible(True)
        self.update_btn.setText("Actualizar")
        self.update_btn.setEnabled(True)
        self.update_progress.setVisible(False)
        self.update_frame.setStyleSheet(
            "QFrame { background: #1f3a2b; border: 1px solid #2f6b45; border-radius: 6px; }"
            "QLabel { color: #dff5e6; }"
        )
        self.update_frame.setVisible(True)
        self._restore_check_updates_btn()
        self._manual_update_check = False

    def _on_update_up_to_date(self) -> None:
        if self._manual_update_check:
            self.update_label.setText(f"Ya estás en la última versión (v{APP_VERSION}).")
            self.update_btn.setVisible(False)
            self.update_progress.setVisible(False)
            self.update_frame.setStyleSheet(
                "QFrame { background: #1f2f3a; border: 1px solid #2f5570; border-radius: 6px; }"
                "QLabel { color: #dfeef5; }"
            )
            self.update_frame.setVisible(True)
        self._restore_check_updates_btn()
        self._manual_update_check = False

    def _on_update_check_failed(self, msg: str) -> None:
        if self._manual_update_check:
            self.update_label.setText(f"No se pudo buscar actualizaciones: {msg}")
            self.update_btn.setVisible(False)
            self.update_progress.setVisible(False)
            self.update_frame.setStyleSheet(
                "QFrame { background: #3a2a1f; border: 1px solid #70502f; border-radius: 6px; }"
                "QLabel { color: #f5eadf; }"
            )
            self.update_frame.setVisible(True)
        self._restore_check_updates_btn()
        self._manual_update_check = False

    def _download_and_apply_update(self) -> None:
        if not self._update_info:
            return
        self.update_btn.setVisible(True)
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Descargando...")
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 0)  # indeterminado hasta recibir bytes
        self._update_dl_worker = UpdateDownloadWorker(self._update_info, self)
        self._update_dl_worker.progress.connect(self._on_update_progress)
        self._update_dl_worker.progress_bytes.connect(self._on_update_progress_bytes)
        self._update_dl_worker.finished_ok.connect(self._on_update_applied)
        self._update_dl_worker.failed.connect(self._on_update_failed)
        self._update_dl_worker.start()

    def _on_update_progress(self, msg: str) -> None:
        self.update_label.setText(msg)

    def _on_update_progress_bytes(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.update_progress.setRange(0, total)
            self.update_progress.setValue(downloaded)
            pct = int(downloaded * 100 / total)
            mb_d = downloaded / (1024 * 1024)
            mb_t = total / (1024 * 1024)
            self.update_progress.setFormat(f"{pct}%  ({mb_d:.0f}/{mb_t:.0f} MB)")
        else:
            # indeterminado (aplicando) o sin total
            if downloaded == 0 and total == 0:
                self.update_progress.setRange(0, 0)
                self.update_progress.setFormat("Aplicando actualización...")
            else:
                self.update_progress.setRange(0, 0)
                mb_d = downloaded / (1024 * 1024)
                self.update_progress.setFormat(f"{mb_d:.0f} MB descargados")

    def _on_update_applied(self, _path: str) -> None:
        import sys
        self.update_progress.setRange(0, 1)
        self.update_progress.setValue(1)
        self.update_progress.setFormat("Actualización aplicada")
        if getattr(sys, "frozen", False):
            self.update_label.setText("Reiniciando...")
            # El updater reemplazará archivos y relanzará la app.
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        else:
            self.update_btn.setText("Descargada")
            self.update_label.setText(
                self.update_label.text() + " (en desarrollo: extraída en _update_extracted/)"
            )

    def _on_update_failed(self, msg: str) -> None:
        self.update_progress.setVisible(False)
        self.update_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Reintentar")
        self.update_label.setText(f"Error al actualizar: {msg}")

    def _open_folder(self) -> None:
        path = self.path_edit.text().strip()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _copy_path(self) -> None:
        QApplication.clipboard().setText(self.path_edit.text().strip())
        self.copy_btn.setText("¡Copiada!")
