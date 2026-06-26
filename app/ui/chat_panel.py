from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 
class GrowingTextEdit(QTextEdit):
    """An input box that grows with its content (1 line up to ``max_lines``,
    then scrolls). Enter sends; Shift+Enter inserts a newline."""

    submitted = Signal()

    def __init__(self, min_lines=6, max_lines=8):
        super().__init__()
        self._min_lines = min_lines  # 初始/最小高度（行数）—— 想改高矮就调它
        self._max_lines = max_lines  # 超过此行数才出现滚动条
        self.setAcceptRichText(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.textChanged.connect(self._adjust_height)
        self._adjust_height()

    def _adjust_height(self):
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        line = self.fontMetrics().lineSpacing()
        # 内容高度夹在 [min_lines, max_lines] 行之间
        content = doc.size().height()
        content = max(self._min_lines * line, min(content, self._max_lines * line))
        margins = self.contentsMargins()
        extra = 2 * self.frameWidth() + margins.top() + margins.bottom() + 4
        self.setFixedHeight(int(content) + extra)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def keyPressEvent(self, event):
        is_enter = event.key() in (Qt.Key_Return, Qt.Key_Enter)
        if is_enter and not (event.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ChatPanel(QWidget):
    """Chat sidebar. Knows nothing about PDF or LLM; it only renders messages
    and emits ``message_submitted`` when the user sends something."""

    message_submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(220)
        self._bubbles = []            # 所有气泡，便于随面板宽度调整
        self._last_ai_bubble = None   # 流式时往里追加的那条 AI 气泡
        self._ai_stream_started = False  # 是否已收到首个片段（用于清掉占位）
        self._busy = False            # 请求中：可继续打字，但不可发送

        title = QLabel("AI 陪读")

        # 消息区：可滚动的气泡列表（竖直堆叠，底部留一个弹性占位顶住）
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        messages = QWidget()
        self._messages_layout = QVBoxLayout(messages)
        self._messages_layout.addStretch()
        self.history_scroll.setWidget(messages)

        self.input = GrowingTextEdit()
        self.input.setPlaceholderText("问点什么…（Enter 发送，Shift+Enter 换行）")
        self.send_btn = QPushButton("发送")

        self.input.submitted.connect(self._submit)
        self.send_btn.clicked.connect(self._submit)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_btn, 0, Qt.AlignBottom)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.history_scroll)
        layout.addLayout(input_row)
        self.setLayout(layout)

    def _submit(self):
        if self._busy:
            return  # 思考中：允许继续打字，但要等回复完成才发送
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def add_message(self, role, text):
        """Render one message as a bubble: user on the right, others on the left."""
        is_user = role == "你"
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setStyleSheet(
            "QLabel {"
            f" background-color: {'#cfe8ff' if is_user else '#eceff1'};"  # 用户淡蓝 / AI 淡灰
            " border-radius: 8px; padding: 6px 10px; }"
        )

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)
        if is_user:
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch()

        # 插在末尾那个弹性占位之前
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, row)
        self._bubbles.append(bubble)
        self._fit_bubble_width(bubble)
        if not is_user:
            self._last_ai_bubble = bubble
        QTimer.singleShot(0, self._scroll_to_bottom)

    def start_ai_message(self):
        """Open an empty AI bubble to be filled by streaming chunks."""
        self.add_message("AI", "…")  # 占位，收到首段后清掉
        self._ai_stream_started = False

    def append_ai_chunk(self, chunk):
        """Append a streamed piece to the current AI bubble."""
        if self._last_ai_bubble is None:
            return
        if not self._ai_stream_started:
            self._last_ai_bubble.setText("")
            self._ai_stream_started = True
        self._last_ai_bubble.setText(self._last_ai_bubble.text() + chunk)
        self._fit_bubble_width(self._last_ai_bubble)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _bubble_max_width(self):
        return max(160, int(self.history_scroll.viewport().width() * 0.8))

    def _fit_bubble_width(self, bubble):
        """Width = content width (hugs short text), capped at max (long text wraps
        only at the edge) — instead of Qt's narrow word-wrap guess."""
        fm = bubble.fontMetrics()
        longest = max(
            (fm.horizontalAdvance(line) for line in bubble.text().split("\n")),
            default=0,
        )
        padding = 28  # 样式表左右内边距 + 一点余量
        target = min(longest + padding, self._bubble_max_width())
        bubble.setFixedWidth(max(48, target))

    def _scroll_to_bottom(self):
        bar = self.history_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for bubble in self._bubbles:
            self._fit_bubble_width(bubble)

    def set_busy(self, busy):
        """Gate sending while a request is in flight, but keep the input typable;
        return focus to it when done so the user can keep typing right away."""
        self._busy = busy
        self.send_btn.setEnabled(not busy)
        self.send_btn.setText("思考中…" if busy else "发送")
        if not busy:
            self.input.setFocus()
