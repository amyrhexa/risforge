"""Entry point for the ``risforge-gui`` command."""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "risforge-gui requires the GUI extras, which aren't installed.\n\n"
            '    pip install "risforge[gui]"\n',
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    from risforge_gui.main_window import MainWindow
    from risforge_gui.theme import Theme, apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("risforge")
    apply_theme(app, Theme.SYSTEM)

    window = MainWindow()
    window.resize(1100, 780)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
