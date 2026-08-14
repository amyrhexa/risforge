"""Entry point for the ``risforge-gui`` command."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    """Launch the risforge desktop application.

    Registered as the ``risforge-gui`` console entry point. The GUI
    extra (PySide6) is optional at the package level, so this is the
    one place that has to tolerate it being absent -- everything past
    the import guard below assumes it's installed.
    """
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        # No logging handler is configured yet at this point (that's
        # normally the CLI's or the GUI's own job, and we haven't
        # reached either), but an unconfigured logger's "last resort"
        # handler still writes ERROR+ to stderr, so this is exactly as
        # visible to the user as a plain print() would have been.
        logger.error(
            "risforge-gui requires the GUI extras, which aren't installed.\n\n"
            '    pip install "risforge[gui]"\n'
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
