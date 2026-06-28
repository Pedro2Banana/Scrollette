import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.config import DEFAULT_PDF
from app.logging_config import setup_logging
from app.ui.main_window import ScrolletteWindow


def main():
    setup_logging()
    app = QApplication(sys.argv)
    window = ScrolletteWindow()
    window.show()

    QTimer.singleShot(0, lambda: window.load_pdf(DEFAULT_PDF))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
