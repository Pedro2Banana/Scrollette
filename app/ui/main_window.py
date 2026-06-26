from PySide6.QtCore import QEvent, Qt, QThread
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_DIR, WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from app.llm.client import LLMClient, SYSTEM_PROMPT
from app.llm.conversation import Conversation
from app.reader.pdf_document import PdfDocument
from app.reader.reading_state import ReadingState
from app.reader.renderer import PdfRenderer
from app.ui.chat_panel import ChatPanel
from app.ui.llm_worker import AskWorker


class ScrolletteWindow(QMainWindow):
    """Main reader window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.document = PdfDocument()
        self.state = ReadingState()
        self.renderer = PdfRenderer()

        self.llm = None  # 延迟创建：没配 key 也能开窗，首次提问时才连
        self.conversation = Conversation(SYSTEM_PROMPT)  # 多轮记忆
        self._thread = None
        self._worker = None
        self._pending_question = ""  # 本轮纯问题，回复完成后存进记忆
        self._reply_chunks = []      # 累积流式回复，用于 record

        self.open_btn = QPushButton("打开 PDF")
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.zoom_out_btn = QPushButton("缩小")
        self.zoom_in_btn = QPushButton("放大")
        self.fit_btn = QPushButton("适应窗口")
        self.two_page_btn = QPushButton("双页")
        self.two_page_btn.setCheckable(True)
        self.sidebar_btn = QPushButton("侧栏")
        self.sidebar_btn.setCheckable(True)
        self.sidebar_btn.setChecked(True)
        self.page_label = QLabel("未打开")

        self.open_btn.clicked.connect(self.open_pdf)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.fit_btn.clicked.connect(self.fit_to_window)
        self.two_page_btn.toggled.connect(self.toggle_two_page)
        self.sidebar_btn.toggled.connect(self.toggle_sidebar)

        toolbar = self.addToolBar("main")
        toolbar.setMovable(False)
        for widget in (
            self.open_btn,
            self.zoom_out_btn,
            self.zoom_in_btn,
            self.fit_btn,
            self.two_page_btn,
            self.page_label,
        ):
            toolbar.addWidget(widget)

        # 弹性占位把“侧栏”按钮顶到工具栏最右侧。
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(self.sidebar_btn)

        self.page_view = QLabel()
        self.page_view.setAlignment(Qt.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.page_view)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.viewport().installEventFilter(self)

        # 阅读区底部居中的翻页条：[上一页] [页码输入] /总页数 [下一页]
        self.page_input = QLineEdit()
        self.page_input.setMaximumWidth(56)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.returnPressed.connect(self.jump_to_page)
        self.total_label = QLabel("/ 0")
        nav = QHBoxLayout()
        nav.addStretch()
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.page_input)
        nav.addWidget(self.total_label)
        nav.addWidget(self.next_btn)
        nav.addStretch()

        reading_side = QWidget()
        reading_layout = QVBoxLayout(reading_side)
        reading_layout.setContentsMargins(0, 0, 0, 0)
        reading_layout.addWidget(self.scroll, 1)
        reading_layout.addLayout(nav)

        self.chat_panel = ChatPanel()
        self.chat_panel.message_submitted.connect(self.on_user_message)

        # 阅读区在左、聊天栏在右；中间的拖柄可调宽度。
        self._sidebar_width = 360
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(reading_side)
        self.splitter.addWidget(self.chat_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([WINDOW_WIDTH - self._sidebar_width, self._sidebar_width])

        self.setCentralWidget(self.splitter)

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
        self.page_input.setText(str(first))
        self.total_label.setText(f"/ {self.document.page_count}")

    def current_text(self):
        """Plain text of the currently visible page(s), for feeding the LLM."""
        if not self.document.is_open:
            return ""
        indices = self.state.visible_indices(self.document.page_count)
        parts = [f"【第 {index + 1} 页】\n{self.document.page_text(index)}" for index in indices]
        return "\n\n".join(parts)

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

    def toggle_sidebar(self, checked):
        if checked:
            self.chat_panel.show()
            self.splitter.setSizes(
                [max(1, self.width() - self._sidebar_width), self._sidebar_width]
            )
        else:
            sizes = self.splitter.sizes()
            if sizes and sizes[-1] > 0:
                self._sidebar_width = sizes[-1]
            self.chat_panel.hide()

    def on_user_message(self, text):
        self.chat_panel.add_message("你", text)

        try:
            client = self._ensure_llm()
        except Exception as exc:
            self.chat_panel.add_message("⚠️", f"AI 不可用：{exc}")
            return

        # 带历史构造本轮请求；记下纯问题、清空回复累积。
        messages = self.conversation.build_request(self.current_text(), text)
        self._pending_question = text
        self._reply_chunks = []

        self.chat_panel.set_busy(True)
        self.chat_panel.start_ai_message()

        # 慢的网络请求丢给 worker 线程，主线程保持响应（可继续翻页等）。
        self._thread = QThread()
        self._worker = AskWorker(client, messages)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_llm_chunk)
        self._worker.finished.connect(self._on_llm_finished)
        self._worker.failed.connect(self._on_llm_error)
        # 收尾：worker 干完 -> 退线程 -> 清理对象
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _ensure_llm(self):
        if self.llm is None:
            self.llm = LLMClient()
        return self.llm

    def _on_llm_chunk(self, piece):
        self._reply_chunks.append(piece)
        self.chat_panel.append_ai_chunk(piece)

    def _on_llm_finished(self):
        # 一轮完成：把（纯问题 + 完整回复）写进记忆。
        self.conversation.record(self._pending_question, "".join(self._reply_chunks))
        self.chat_panel.set_busy(False)

    def _on_llm_error(self, message):
        self.chat_panel.append_ai_chunk(f"⚠️ 调用失败：{message}")
        self.chat_panel.set_busy(False)

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

    def jump_to_page(self):
        if not self.document.is_open:
            return
        text = self.page_input.text().strip()
        if not text.isdigit():
            self.render_page()  # 输入非法则还原显示
            return
        target = max(0, min(int(text) - 1, self.document.page_count - 1))
        self.state.page_index = target
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
