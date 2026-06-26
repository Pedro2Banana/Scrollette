from PySide6.QtCore import QObject, Signal


class AskWorker(QObject):
    """Runs one ``LLMClient.ask()`` call off the main thread and reports back
    via signals. Lives in the UI layer so that ``app/llm`` stays Qt-free."""

    chunk = Signal(str)     # 流式：每次一小段回复文本
    finished = Signal()     # 成功：整段结束（文本已通过 chunk 逐段发出）
    failed = Signal(str)    # 失败：携带错误信息

    def __init__(self, client, messages):
        super().__init__()
        self._client = client
        self._messages = messages

    def run(self):
        try:
            for piece in self._client.ask_stream(self._messages):
                self.chunk.emit(piece)
            self.finished.emit()
        except Exception as exc:  # 网络/鉴权等任何异常都不该让程序崩
            self.failed.emit(str(exc))
