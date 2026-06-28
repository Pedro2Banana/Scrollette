import datetime
import logging

from PySide6.QtCore import QEvent, QPointF, Qt, QThread, QTimer
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

from app.config import BOOKS_DIR, WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from app.llm.client import LLMClient, SYSTEM_PROMPT
from app.llm.conversation import Conversation
from app.rag.service import RagService
from app.storage.reading_store import ReadingStore
from app.reader.pdf_document import PdfDocument
from app.reader.reading_state import ReadingState
from app.reader.renderer import PdfRenderer
from app.ui.chat_panel import ChatPanel
from app.ui.llm_worker import AskWorker, IndexWorker

logger = logging.getLogger(__name__)


class ScrolletteWindow(QMainWindow):
    """Main reader window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.document = PdfDocument()
        self.state = ReadingState()
        self.renderer = PdfRenderer()
        self.reading_store = ReadingStore()

        self.llm = None  # 延迟创建：没配 key 也能开窗，首次提问时才连
        self.conversation = Conversation(SYSTEM_PROMPT)  # 多轮记忆
        self._rag = None         # 延迟创建的 RagService
        self._rag_ready = True   # 创建失败则置 False，不再重试
        self._max_read_page = 0  # 读到过的最大页，companion 检索用
        self._thread = None
        self._worker = None
        self._pending_question = ""  # 本轮纯问题，回复完成后存进记忆
        self._reply_chunks = []      # 累积流式回复，用于 record
        self._panning = False        # 是否正在拖动平移页面
        self._pan_start = None

        # 后台增量索引：落到某页 0.8s 后才索引，避免快速翻页时频繁触发。
        self._indexing = False
        self._index_thread = None
        self._index_worker = None
        self._index_timer = QTimer(self)
        self._index_timer.setSingleShot(True)
        self._index_timer.setInterval(800)
        self._index_timer.timeout.connect(self._index_current_pages)

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
        self.index_label = QLabel("")  # 后台索引状态提示

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
            self.index_label,
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
        self.scroll.viewport().setCursor(Qt.OpenHandCursor)  # 提示可拖动

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
        self.conversation.clear()  # 换书清空对话记忆
        # 登记这本书 + 从库恢复阅读进度（companion 检索范围）
        doc_id = self.document.file_hash
        self.reading_store.upsert_document(
            doc_id, self.document.path.name, self.document.page_count
        )
        self._max_read_page = self.reading_store.max_read_page(doc_id)
        # 续读：恢复上次停留页 + 单/双页
        last_page, two_page = self.reading_store.view_state(doc_id)
        self.state.two_page = two_page
        self.two_page_btn.blockSignals(True)
        self.two_page_btn.setChecked(two_page)
        self.two_page_btn.blockSignals(False)
        self.state.page_index = min(max(0, last_page - 1), self.document.page_count - 1)
        self.fit_to_window()

    def open_pdf(self):
        start_dir = self.document.path.parent if self.document.path else BOOKS_DIR
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
        self._max_read_page = max(self._max_read_page, last)
        self._index_timer.start()  # 防抖：稳定停在本页后再后台索引

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
        self._zoom_at(1.2, self._viewport_center())

    def zoom_out(self):
        self._zoom_at(1 / 1.2, self._viewport_center())

    def _viewport_center(self):
        vp = self.scroll.viewport()
        return QPointF(vp.width() / 2, vp.height() / 2)

    def _zoom_at(self, factor, viewport_pos):
        """Zoom keeping the content point under ``viewport_pos`` fixed on screen."""
        if not self.document.is_open:
            return
        old_zoom = self.state.zoom
        # 光标下的点，在缩放前的“内容坐标”里的位置
        point = self.page_view.mapFrom(self.scroll.viewport(), viewport_pos.toPoint())
        self.state.zoom = max(0.1, old_zoom * factor)
        self.render_page()
        scale = self.state.zoom / old_zoom
        self.scroll.horizontalScrollBar().setValue(int(point.x() * scale - viewport_pos.x()))
        self.scroll.verticalScrollBar().setValue(int(point.y() * scale - viewport_pos.y()))

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

        self._pending_question = text
        self._reply_chunks = []
        logger.info("收到提问（当前页范围≤%d）：%s", self._max_read_page, text)

        self.chat_panel.set_busy(True)
        self.chat_panel.start_ai_message()

        # 检索 + LLM + 工具循环都是慢活，整体丢给 worker 线程，主线程保持响应。
        document_id = self.document.file_hash if self.document.is_open else None
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self._thread = QThread()
        self._worker = AskWorker(
            client,
            self.conversation,
            self.current_text(),
            text,
            rag=self._ensure_rag(),
            store=self.reading_store,
            document_id=document_id,
            max_read_page=self._max_read_page,
            today=today,
        )
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

    def _ensure_rag(self):
        # 创建失败（如 Chroma 出错）不该挡住聊天，返回 None 即可退回纯当前页问答。
        if self._rag is None and self._rag_ready:
            try:
                self._rag = RagService()
            except Exception:
                self._rag_ready = False
        return self._rag

    def _index_current_pages(self):
        if not self.document.is_open:
            return
        if self._indexing:
            self._index_timer.start()  # 上一批还在跑，稍后再试
            return

        indices = self.state.visible_indices(self.document.page_count)
        document_id = self.document.file_hash

        # 记阅读（停下来就算读过）——SQLite，主线程，快
        for i in indices:
            self.reading_store.mark_read(document_id, i + 1)
            self._max_read_page = max(self._max_read_page, i + 1)
        self.reading_store.save_view_state(document_id, indices[0] + 1, self.state.two_page)

        # 后台向量索引（仅当 RAG 可用）
        rag = self._ensure_rag()
        if not rag:
            return
        pages = [(i + 1, self.document.page_text(i)) for i in indices]
        self._indexing = True
        self.index_label.setText("索引中…")
        self._index_thread = QThread()
        self._index_worker = IndexWorker(rag, document_id, pages)
        self._index_worker.moveToThread(self._index_thread)
        self._index_thread.started.connect(self._index_worker.run)
        self._index_worker.done.connect(self._on_index_finished)
        self._index_worker.failed.connect(self._on_index_finished)
        self._index_worker.done.connect(self._index_thread.quit)
        self._index_worker.failed.connect(self._index_thread.quit)
        self._index_thread.finished.connect(self._index_worker.deleteLater)
        self._index_thread.finished.connect(self._index_thread.deleteLater)
        self._index_thread.start()

    def _on_index_finished(self, *args):
        self._indexing = False
        self.index_label.setText("")

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
            factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            self._zoom_at(factor, event.position())  # 以光标位置为焦点
            return True
        # 拖动平移：按下记录起点 + 当前滚动量；移动时反向调滚动条。
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._panning = True
            self._pan_start = event.position()
            self._pan_h = self.scroll.horizontalScrollBar().value()
            self._pan_v = self.scroll.verticalScrollBar().value()
            self.scroll.viewport().setCursor(Qt.ClosedHandCursor)
            return True
        if event.type() == QEvent.MouseMove and self._panning:
            delta = event.position() - self._pan_start
            self.scroll.horizontalScrollBar().setValue(self._pan_h - int(delta.x()))
            self.scroll.verticalScrollBar().setValue(self._pan_v - int(delta.y()))
            return True
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._panning = False
            self.scroll.viewport().setCursor(Qt.OpenHandCursor)
            return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self.document.is_open:
            self.reading_store.save_view_state(
                self.document.file_hash, self.state.page_index + 1, self.state.two_page
            )
        self.document.close()
        self.reading_store.close()
        super().closeEvent(event)
