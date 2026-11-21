"""Punto de entrada de la interfaz gráfica AVANZADA (editor completo).

Uso:
    python gui_avanzada.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from gui import icon_path
    from gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Subtítulos automáticos (avanzado)")

    icon = icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))

    window = MainWindow()
    if icon:
        window.setWindowIcon(QIcon(icon))
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
