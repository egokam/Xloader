"""PySide6 application bootstrap and stylesheet live reload."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .window import SideloadlyWindow, STYLESHEET

APP_ICON = Path(__file__).parent / "assets" / "app-icon.svg"


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Xloader")
    app.setOrganizationName("Xloader")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(["SF Pro Text", "Helvetica Neue", "Segoe UI", "Arial"])
    font.setPixelSize(15)
    app.setFont(font)

    try:
        app.setStyleSheet(STYLESHEET.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"Could not load Xloader stylesheet: {error}", file=sys.stderr)

    development_preview = os.environ.get("XLOADER_DEV_PREVIEW") == "1"
    window = SideloadlyWindow(development_preview=development_preview)
    window.show()

    if development_preview:
        last_modified = STYLESHEET.stat().st_mtime_ns if STYLESHEET.exists() else 0
        reload_timer = QTimer(window)

        def reload_stylesheet() -> None:
            nonlocal last_modified
            try:
                current_modified = STYLESHEET.stat().st_mtime_ns
                if current_modified == last_modified:
                    return
                stylesheet = STYLESHEET.read_text(encoding="utf-8")
            except OSError as error:
                print(f"[preview] Stylesheet reload failed: {error}", file=sys.stderr, flush=True)
                return
            app.setStyleSheet(stylesheet)
            last_modified = current_modified
            print("[preview] Stylesheet reloaded", flush=True)

        reload_timer.timeout.connect(reload_stylesheet)
        reload_timer.start(250)
        print("[preview] PySide6 stylesheet live reload enabled", flush=True)

    sys.exit(app.exec())
