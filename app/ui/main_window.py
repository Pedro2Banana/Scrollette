from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_DIR, WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from app.reader.pdf_document import PdfDocument
from app.reader.reading_state import ReadingState
from app.reader.renderer import PdfRenderer


class ScrolletteWindow(QMainWindow):
    """Main reader window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.document = PdfDocument()
        self.state = ReadingState()
        self.renderer = PdfRenderer()

        self.open_btn = QPushButton("打开 PDF")
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.zoom_out_btn = QPushButton("缩小")
        self.zoom_in_btn = QPushButton("放大")
        self.fit_btn = QPushButton("适应窗口")
        self.two_page_btn = QPushButton("双页")
        self.two_page_btn.setCheckable(True)
        self.page_label = QLabel("未打开")

        self.open_btn.clicked.connect(self.open_pdf)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.fit_btn.clicked.connect(self.fit_to_window)
        self.two_page_btn.toggled.connect(self.toggle_two_page)

        toolbar = QHBoxLayout()
        for widget in (
            self.open_btn,
            self.prev_btn,
            self.next_btn,
            self.zoom_out_btn,
            self.zoom_in_btn,
            self.fit_btn,
            self.two_page_btn,
            self.page_label,
        ):
            toolbar.addWidget(widget)
        toolbar.addStretch()

        self.page_view = QLabel()
        self.page_view.setAlignment(Qt.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.page_view)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.viewport().installEventFilter(self)

        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._prev_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._prev_shortcut.activated.connect(self.prev_page)
        self._next_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._next_shortcut.activated.connect(self.next_page)

    def load_pdf(self, path):
        try:
            self.document.open(path)
        except FileNotFoundError:
            return

        self.state.reset_for_new_document()
        self.fit_to_window()

    def open_pdf(self):
        start_dir = self.document.path.parent if self.document.path else APP_DIR
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", str(start_dir), "PDF (*.pdf)")
        if path:
            self.load_pdf(path)

    def render_page(self):
        if not self.document.is_open:
            return

        indices = self.state.visible_indices(self.document.page_count)
        images = [
            self.renderer.render_page(self.document.page(index), self.state.zoom)
            for index in indices
        ]
        self.page_view.setPixmap(QPixmap.fromImage(self.renderer.combine(images)))
        self.page_view.adjustSize()

        first, last = indices[0] + 1, indices[-1] + 1
        page_range = f"{first}" if first == last else f"{first}-{last}"
        self.page_label.setText(
            f"第 {page_range} / {self.document.page_count} 页  ({int(self.state.zoom * 100)}%)"
        )

    def fit_to_window(self):
        if not self.document.is_open:
            return

        page = self.document.page(self.state.page_index)
        page_width = page.rect.width * (2 if self.state.two_page else 1)
        page_height = page.rect.height
        viewport_width = self.scroll.viewport().width() - 24
        viewport_height = self.scroll.viewport().height() - 24

        self.state.zoom = max(0.1, min(viewport_width / page_width, viewport_height / page_height))
        self.render_page()

    def zoom_in(self):
        if self.document.is_open:
            self.state.zoom *= 1.2
            self.render_page()

    def zoom_out(self):
        if self.document.is_open:
            self.state.zoom /= 1.2
            self.render_page()

    def toggle_two_page(self, checked):
        self.state.two_page = checked
        self.fit_to_window()

    def prev_page(self):
        if not self.document.is_open:
            return
        self.state.previous_page()
        self.render_page()

    def next_page(self):
        if not self.document.is_open:
            return
        self.state.next_page(self.document.page_count)
        self.render_page()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and (event.modifiers() & Qt.ControlModifier):
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.document.close()
        super().closeEvent(event)
