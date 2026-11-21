"""Ventana principal de la interfaz gráfica."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exporters import to_ass, to_srt, to_vegas_csv
from core.subtitles import SubtitleCue

from .timeutil import fmt_time, parse_time
from .waveform import WaveformWidget
from .worker import TranscribeWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtítulos automáticos — Whisper local")
        self.resize(1100, 720)

        self._cues: list[SubtitleCue] = []
        self._input_path: str | None = None
        self._audio_path: str | None = None
        self._loading = False
        self._worker: TranscribeWorker | None = None

        self._build_ui()
        self._build_toolbar()
        self._setup_player()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(self._build_settings())

        self.waveform = WaveformWidget()
        self.waveform.seekRequested.connect(self._on_seek)
        root.addWidget(self.waveform)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Inicio", "Fin", "Duración", "Texto"])
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        root.addWidget(self.table, 1)

        self.statusBar().showMessage("Abre un archivo de video/audio para empezar.")

    def _build_settings(self) -> QGroupBox:
        box = QGroupBox("Ajustes")
        form = QFormLayout(box)

        self.model_combo = QComboBox()
        self.model_combo.addItems(
            ["large-v3", "large-v2", "medium", "small", "base", "tiny", "distil-large-v3"]
        )
        self.model_combo.setCurrentText("large-v3")
        form.addRow("Modelo:", self.model_combo)

        self.language_combo = QComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.addItems(["es", "en", "pt", "fr", "de", "it", "auto"])
        self.language_combo.setCurrentText("es")
        form.addRow("Idioma:", self.language_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cuda", "cpu"])
        form.addRow("Dispositivo:", self.device_combo)

        self.fps_combo = QComboBox()
        self.fps_combo.setEditable(True)
        self.fps_combo.addItems(["60", "59.94", "30", "29.97", "25", "24", "23.976", "50"])
        self.fps_combo.setCurrentText("60")
        form.addRow("FPS (Vegas):", self.fps_combo)

        self.max_words_spin = QSpinBox()
        self.max_words_spin.setRange(1, 10)
        self.max_words_spin.setValue(3)
        form.addRow("Máx. palabras/línea:", self.max_words_spin)

        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(5, 100)
        self.max_chars_spin.setValue(18)
        form.addRow("Máx. caracteres/línea:", self.max_chars_spin)

        self.max_gap_spin = QDoubleSpinBox()
        self.max_gap_spin.setRange(0.1, 2.0)
        self.max_gap_spin.setSingleStep(0.05)
        self.max_gap_spin.setValue(0.4)
        form.addRow("Pausa para cortar (s):", self.max_gap_spin)

        self.min_dur_spin = QDoubleSpinBox()
        self.min_dur_spin.setRange(0.1, 2.0)
        self.min_dur_spin.setSingleStep(0.05)
        self.min_dur_spin.setValue(0.3)
        form.addRow("Duración mínima (s):", self.min_dur_spin)

        self.max_dur_spin = QDoubleSpinBox()
        self.max_dur_spin.setRange(1.0, 15.0)
        self.max_dur_spin.setSingleStep(0.5)
        self.max_dur_spin.setValue(4.0)
        form.addRow("Duración máxima (s):", self.max_dur_spin)

        return box

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Principal")
        tb.setMovable(False)

        self.open_action = QAction("Abrir archivo", self)
        self.open_action.triggered.connect(self._open_file)
        tb.addAction(self.open_action)

        self.transcribe_action = QAction("Transcribir", self)
        self.transcribe_action.triggered.connect(self._transcribe)
        tb.addAction(self.transcribe_action)

        tb.addSeparator()

        self.play_action = QAction("Reproducir/Pausa", self)
        self.play_action.triggered.connect(self._toggle_play)
        tb.addAction(self.play_action)

        self.stop_action = QAction("Detener", self)
        self.stop_action.triggered.connect(self._stop)
        tb.addAction(self.stop_action)

        tb.addSeparator()

        self.export_srt = QAction("Exportar SRT", self)
        self.export_srt.triggered.connect(lambda: self._export("srt"))
        tb.addAction(self.export_srt)

        self.export_ass = QAction("Exportar ASS", self)
        self.export_ass.triggered.connect(lambda: self._export("ass"))
        tb.addAction(self.export_ass)

        self.export_vegas = QAction("Exportar Vegas CSV", self)
        self.export_vegas.triggered.connect(lambda: self._export("vegas"))
        tb.addAction(self.export_vegas)

        tb.addSeparator()

        self.upper_action = QAction("MAYÚSCULAS", self)
        self.upper_action.setShortcut(QKeySequence("Ctrl+Shift+U"))
        self.upper_action.triggered.connect(lambda: self._apply_case(True))
        tb.addAction(self.upper_action)

        self.lower_action = QAction("minúsculas", self)
        self.lower_action.setShortcut(QKeySequence("Ctrl+U"))
        self.lower_action.triggered.connect(lambda: self._apply_case(False))
        tb.addAction(self.lower_action)

        tb.addSeparator()

        self.save_action = QAction("Guardar proyecto", self)
        self.save_action.triggered.connect(self._save_project)
        tb.addAction(self.save_action)

        self.load_action = QAction("Cargar proyecto", self)
        self.load_action.triggered.connect(self._load_project)
        tb.addAction(self.load_action)

    def _setup_player(self) -> None:
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._update_playhead)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir archivo de video/audio",
            "",
            "Medios (*.mp4 *.mkv *.mov *.avi *.mp3 *.wav *.m4a *.flac *.aac);;Todos (*.*)",
        )
        if not path:
            return
        self._input_path = path
        self.setWindowTitle(f"Subtítulos automáticos — {Path(path).name}")
        self.statusBar().showMessage(f"Archivo cargado: {path}")

    def _transcribe(self) -> None:
        if not self._input_path:
            QMessageBox.warning(self, "Sin archivo", "Primero abre un archivo de video/audio.")
            return

        fps = float(self.fps_combo.currentText().strip() or "60")

        self._worker = TranscribeWorker(
            self._input_path,
            model=self.model_combo.currentText(),
            language=self.language_combo.currentText().strip(),
            device=self.device_combo.currentText(),
            max_words=self.max_words_spin.value(),
            max_chars=self.max_chars_spin.value(),
            max_gap=self.max_gap_spin.value(),
            min_duration=self.min_dur_spin.value(),
            max_duration=self.max_dur_spin.value(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self.transcribe_action.setEnabled(False)
        self.open_action.setEnabled(False)
        self._worker.start()

    def _on_progress(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _on_finished(self, cues: list, audio_path: str, info: dict) -> None:
        self._cues = list(cues)
        self._audio_path = audio_path

        self.waveform.set_audio(audio_path)
        self.waveform.set_cues(self._cues)
        self._populate_table()

        self._player.setSource(QUrl.fromLocalFile(audio_path))

        lang = info.get("language", "?")
        prob = info.get("language_probability", 0.0)
        self.statusBar().showMessage(
            f"Listo: {len(cues)} subtítulos · idioma {lang} (prob. {prob:.2f})"
        )
        self.transcribe_action.setEnabled(True)
        self.open_action.setEnabled(True)

    def _on_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)
        self.transcribe_action.setEnabled(True)
        self.open_action.setEnabled(True)
        self.statusBar().showMessage("Error en la transcripción.")

    # ------------------------------------------------------------------
    # Tabla
    # ------------------------------------------------------------------
    def _populate_table(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        for i, cue in enumerate(self._cues):
            self.table.insertRow(i)

            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, idx_item)

            self.table.setItem(i, 1, QTableWidgetItem(fmt_time(cue.start)))
            self.table.setItem(i, 2, QTableWidgetItem(fmt_time(cue.end)))

            dur_item = QTableWidgetItem(fmt_time(max(cue.end - cue.start, 0.0)))
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 3, dur_item)

            self.table.setItem(i, 4, QTableWidgetItem(cue.text))
        self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._cues):
            return
        cue = self._cues[row]

        if col == 1:  # Inicio
            try:
                cue.start = parse_time(item.text())
            except ValueError:
                self._revert(item, fmt_time(cue.start))
        elif col == 2:  # Fin
            try:
                cue.end = parse_time(item.text())
            except ValueError:
                self._revert(item, fmt_time(cue.end))
        elif col == 4:  # Texto
            cue.text = item.text().strip()

        self._update_duration(row)
        self.waveform.set_cues(self._cues)

    def _revert(self, item: QTableWidgetItem, text: str) -> None:
        self._loading = True
        item.setText(text)
        self._loading = False

    def _update_duration(self, row: int) -> None:
        cue = self._cues[row]
        self._loading = True
        self.table.item(row, 3).setText(fmt_time(max(cue.end - cue.start, 0.0)))
        self._loading = False

    def _on_selection_changed(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        if 0 <= row < len(self._cues):
            self.waveform.set_highlight(row)
            self._seek(self._cues[row].start)

    def _apply_case(self, upper: bool) -> None:
        for item in self.table.selectedItems():
            if item.column() == 4:
                new = item.text().upper() if upper else item.text().lower()
                if new != item.text():
                    item.setText(new)

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------
    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()
            self._timer.start()

    def _stop(self) -> None:
        self._player.stop()
        self._timer.stop()
        self.waveform.set_playhead(0.0)

    def _seek(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))
        self.waveform.set_playhead(seconds)

    def _on_seek(self, seconds: float) -> None:
        self._seek(seconds)

    def _update_playhead(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self.waveform.set_playhead(self._player.position() / 1000.0)
        else:
            self._timer.stop()

    # ------------------------------------------------------------------
    # Exportar
    # ------------------------------------------------------------------
    def _export(self, kind: str) -> None:
        if not self._cues:
            QMessageBox.warning(self, "Sin subtítulos", "No hay subtítulos para exportar.")
            return

        base = Path(self._input_path).with_suffix("") if self._input_path else Path("subtitulos")
        default = str(base)

        if kind == "srt":
            path, _ = QFileDialog.getSaveFileName(self, "Exportar SRT", default + ".srt", "SRT (*.srt)")
            if not path:
                return
            Path(path).write_text(to_srt(self._sorted_cues()), encoding="utf-8")
        elif kind == "ass":
            path, _ = QFileDialog.getSaveFileName(self, "Exportar ASS", default + ".ass", "ASS (*.ass)")
            if not path:
                return
            Path(path).write_text(to_ass(self._sorted_cues()), encoding="utf-8")
        elif kind == "vegas":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar Vegas CSV", default + ".vegas.csv", "CSV (*.csv)"
            )
            if not path:
                return
            fps = float(self.fps_combo.currentText().strip() or "60")
            Path(path).write_text(to_vegas_csv(self._sorted_cues(), fps=fps), encoding="utf-8")

        self.statusBar().showMessage(f"Exportado: {path}")

    def _sorted_cues(self) -> list[SubtitleCue]:
        cues = sorted(self._cues, key=lambda c: c.start)
        for i, c in enumerate(cues, start=1):
            c.index = i
        return cues

    # ------------------------------------------------------------------
    # Proyecto (guardar/cargar)
    # ------------------------------------------------------------------
    def _save_project(self) -> None:
        if not self._cues:
            QMessageBox.warning(self, "Sin subtítulos", "No hay nada que guardar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", "", "Proyecto (*.json)")
        if not path:
            return
        data = {
            "input": self._input_path,
            "audio": self._audio_path,
            "fps": self.fps_combo.currentText().strip(),
            "cues": [
                {"start": c.start, "end": c.end, "text": c.text} for c in self._cues
            ],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"Proyecto guardado: {path}")

    def _load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar proyecto", "", "Proyecto (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Error", f"No se pudo leer el proyecto:\n{exc}")
            return

        self._cues = [
            SubtitleCue(index=i, start=c["start"], end=c["end"], text=c["text"])
            for i, c in enumerate(data.get("cues", []), start=1)
        ]
        self._input_path = data.get("input")
        audio = data.get("audio")
        if audio and Path(audio).exists():
            self._audio_path = audio
            self.waveform.set_audio(audio)
            self._player.setSource(QUrl.fromLocalFile(audio))
        else:
            self._audio_path = None
            self.waveform.set_audio(None)
            self._player.setSource(QUrl())

        fps = str(data.get("fps", "60"))
        self.fps_combo.setCurrentText(fps)

        self.waveform.set_cues(self._cues)
        self._populate_table()
        self.statusBar().showMessage(f"Proyecto cargado: {path}")

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self._player.stop()
        super().closeEvent(event)
