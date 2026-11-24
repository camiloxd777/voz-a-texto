"""Punto de entrada de la interfaz gráfica (versión simple).

Uso:
    python gui.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from core.logging_setup import get_logger, log_file, setup_logging

    setup_logging()
    log = get_logger("gui")
    log.info("App iniciando (versión %s)", _version_string())

    def excepthook(exc_type, exc_value, exc_tb):
        import traceback
        log.error("Excepción no capturada:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = excepthook

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from gui import icon_path
    from gui.simple_window import SimpleWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Subtítulos automáticos")

    icon = icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))

    window = SimpleWindow()
    if icon:
        window.setWindowIcon(QIcon(icon))
    window.show()

    return app.exec()


def _version_string() -> str:
    try:
        from core.version import APP_VERSION
        return APP_VERSION
    except Exception:
        return "?"


if __name__ == "__main__":
    raise SystemExit(main())
