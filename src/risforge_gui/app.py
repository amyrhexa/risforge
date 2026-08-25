"""Application entry point for risforge-gui."""

from __future__ import annotations

import logging
import sys


def main() -> int:
    """Launch the risforge GUI."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write("risforge-gui requires the GUI extras: pip install 'risforge[gui]'\n")
        return 1

    from risforge_gui.main_window import MainWindow
    from risforge_gui.theme import Theme, apply_theme

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger("risforge_gui")
    logger.info("Starting risforge-gui")

    app = QApplication(sys.argv)
    app.setApplicationName("RisForge")
    app.setOrganizationName("Amyr")

    apply_theme(app, Theme.SYSTEM)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
