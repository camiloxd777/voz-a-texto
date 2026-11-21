"""Diálogo de revisión antes de exportar (sin audio)."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.subtitles import SubtitleCue

from .timeutil import fmt_time, parse_time


# Puntuación básica (puntos, comas, punto y coma, dos puntos, etc.)
_PUNCT_BASIC_RE = re.compile(r"[.,;:…]")
# Exclamaciones e interrogaciones (incluye apertura en español)
_PUNCT_EXCL_QUEST_RE = re.compile(r"[!¡?¿]")


def _strip_punct_basic(text: str) -> str:
    cleaned = _PUNCT_BASIC_RE.sub("", text)
    cleaned = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in cleaned.split("\n"))
    return cleaned.strip()


def _strip_punct_excl_quest(text: str) -> str:
    cleaned = _PUNCT_EXCL_QUEST_RE.sub("", text)
    cleaned = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in cleaned.split("\n"))
    return cleaned.strip()


def _title_case(text: str) -> str:
    # Capitaliza la primera letra de cada palabra, sin romper apóstrofes.
    def cap_word(w: str) -> str:
        for i, ch in enumerate(w):
            if ch.isalpha():
                return w[:i] + ch.upper() + w[i + 1 :].lower()
        return w

    return "\n".join(
        " ".join(cap_word(w) for w in ln.split(" ")) for ln in text.split("\n")
    )


def _apply_case(text: str, mode: str) -> str:
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return _title_case(text)
    return text  # normal


def _split_words(text: str) -> list[str]:
    # Separar por espacios/saltos de línea conservando palabras.
    return [t for t in re.split(r"\s+", text.strip()) if t]


class ReviewDialog(QDialog):
    """Permite revisar/editar subtítulos antes de generar el archivo final."""

    def __init__(self, cues: list[SubtitleCue], info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisar subtítulos antes de generar")
        self.resize(920, 620)

        self._cues: list[SubtitleCue] = [
            SubtitleCue(index=c.index, start=c.start, end=c.end, text=c.text) for c in cues
        ]
        self._info = info
        self._loading = False

        self._build_ui()
        self._populate_table()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        title = QLabel("Revisa los subtítulos antes de generar el archivo")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        root.addWidget(title)

        hint = QLabel(
            "Edita el texto si hace falta. Puedes mover la última palabra al siguiente "
            "subtítulo o subir la primera palabra al anterior."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa;")
        root.addWidget(hint)

        # Tabla editable
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Inicio", "Fin", "Texto"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 110)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        # Acciones de edición de palabras
        word_row = QHBoxLayout()
        word_row.addWidget(QLabel("Mover palabras:"))
        self.move_down_btn = QPushButton("Bajar última palabra ↓")
        self.move_down_btn.setToolTip("Mueve la última palabra del subtítulo seleccionado al siguiente")
        self.move_down_btn.clicked.connect(self._move_last_word_down)
        word_row.addWidget(self.move_down_btn)

        self.move_up_btn = QPushButton("Subir primera palabra ↑")
        self.move_up_btn.setToolTip("Mueve la primera palabra del subtítulo seleccionado al anterior")
        self.move_up_btn.clicked.connect(self._move_first_word_up)
        word_row.addWidget(self.move_up_btn)

        word_row.addStretch(1)
        root.addLayout(word_row)

        # Opciones de formato de texto
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Texto:"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(["Texto normal", "todo minúsculas", "TODO MAYÚSCULAS", "Tipo Título"])
        fmt_row.addWidget(self.case_combo)

        self.punct_basic_check = QCheckBox("Quitar puntuación (.,;:)")
        fmt_row.addWidget(self.punct_basic_check)

        self.punct_excl_check = QCheckBox("Quitar exclamaciones e interrogaciones (¡!¿?)")
        fmt_row.addWidget(self.punct_excl_check)

        fmt_row.addStretch(1)
        root.addLayout(fmt_row)

        # Botones finales
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.generate_btn = QPushButton("Generar archivo")
        self.generate_btn.setDefault(True)
        self.generate_btn.setMinimumHeight(36)
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)

        root.addLayout(btn_row)

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
            self.table.setItem(i, 3, QTableWidgetItem(cue.text))
        self._loading = False

    def _refresh_table(self) -> None:
        self._loading = True
        # Ajustar filas si cambió la cantidad (por si acaso)
        if self.table.rowCount() != len(self._cues):
            self._populate_table()
            return
        for i, cue in enumerate(self._cues):
            self.table.item(i, 0).setText(str(i + 1))
            self.table.item(i, 1).setText(fmt_time(cue.start))
            self.table.item(i, 2).setText(fmt_time(cue.end))
            self.table.item(i, 3).setText(cue.text)
        self._loading = False

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._cues):
            return
        cue = self._cues[row]

        if col == 1:
            try:
                cue.start = parse_time(item.text())
            except ValueError:
                self._revert(item, fmt_time(cue.start))
        elif col == 2:
            try:
                cue.end = parse_time(item.text())
            except ValueError:
                self._revert(item, fmt_time(cue.end))
        elif col == 3:
            cue.text = item.text().strip()

    def _revert(self, item: QTableWidgetItem, text: str) -> None:
        self._loading = True
        item.setText(text)
        self._loading = False

    # ------------------------------------------------------------------
    # Mover palabras entre subtítulos
    def _selected_row(self) -> int:
        items = self.table.selectedItems()
        if not items:
            return -1
        return items[0].row()

    def _move_last_word_down(self) -> None:
        row = self._selected_row()
        if row < 0 or row >= len(self._cues) - 1:
            return
        src = self._cues[row]
        dst = self._cues[row + 1]
        src_words = _split_words(src.text)
        if len(src_words) <= 1:
            return
        moved = src_words[-1]
        src.text = " ".join(src_words[:-1])
        dst_words = _split_words(dst.text)
        dst.text = " ".join([moved] + dst_words)

        # Ajuste simple de tiempos: repartir proporcionalmente en src.
        src_dur = max(src.end - src.start, 0.0)
        if src_dur > 0 and len(src_words) > 0:
            # quitar proporción de 1 palabra al final de src
            per = src_dur / len(src_words)
            src.end = max(src.start + 0.1, src.end - per)
        # extender inicio de dst ligeramente hacia atrás si hay hueco
        if dst.start > src.end:
            dst.start = src.end

        self._refresh_table()
        self.table.selectRow(row)

    def _move_first_word_up(self) -> None:
        row = self._selected_row()
        if row <= 0 or row >= len(self._cues):
            return
        src = self._cues[row]
        dst = self._cues[row - 1]
        src_words = _split_words(src.text)
        if len(src_words) <= 1:
            return
        moved = src_words[0]
        src.text = " ".join(src_words[1:])
        dst_words = _split_words(dst.text)
        dst.text = " ".join(dst_words + [moved])

        # Ajuste simple de tiempos
        src_dur = max(src.end - src.start, 0.0)
        if src_dur > 0 and len(src_words) > 0:
            per = src_dur / len(src_words)
            src.start = min(src.end - 0.1, src.start + per)
        if dst.end < src.start:
            dst.end = src.start

        self._refresh_table()
        self.table.selectRow(row)

    # ------------------------------------------------------------------
    def _apply_text_formatting(self) -> None:
        case_mode = {
            "Texto normal": "normal",
            "todo minúsculas": "lower",
            "TODO MAYÚSCULAS": "upper",
            "Tipo Título": "title",
        }.get(self.case_combo.currentText(), "normal")

        strip_basic = self.punct_basic_check.isChecked()
        strip_excl = self.punct_excl_check.isChecked()

        for cue in self._cues:
            text = cue.text
            if strip_basic:
                text = _strip_punct_basic(text)
            if strip_excl:
                text = _strip_punct_excl_quest(text)
            text = _apply_case(text, case_mode)
            cue.text = text

    def _on_generate(self) -> None:
        self._apply_text_formatting()
        # Reindexar
        for i, cue in enumerate(self._cues, 1):
            cue.index = i
        self.accept()

    def result_cues(self) -> list[SubtitleCue]:
        return self._cues
