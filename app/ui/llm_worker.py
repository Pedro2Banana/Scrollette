from PySide6.QtCore import QObject, Signal


class AskWorker(QObject):
    """Produces one answer off the main thread: (optional) RAG retrieval →
    build the request → stream the LLM reply. All network work lives here so
    the UI never freezes. Lives in the UI layer so ``app/llm`` stays Qt-free."""

    chunk = Signal(str)     # 流式：每次一小段回复文本
    finished = Signal()     # 成功：整段结束（文本已通过 chunk 逐段发出）
    failed = Signal(str)    # 失败：携带错误信息

    def __init__(
        self,
        client,
        conversation,
        page_text,
        question,
        rag=None,
        document_id=None,
        max_read_page=None,
    ):
        super().__init__()
        self._client = client
        self._conversation = conversation
        self._page_text = page_text
        self._question = question
        self._rag = rag
        self._document_id = document_id
        self._max_read_page = max_read_page

    def run(self):
        try:
            chunks = None
            if self._rag and self._document_id:
                chunks = self._rag.retrieve(
                    self._question, self._document_id, self._max_read_page
                )
            messages = self._conversation.build_request(
                self._page_text, self._question, chunks
            )
            for piece in self._client.ask_stream(messages):
                self.chunk.emit(piece)
            self.finished.emit()
        except Exception as exc:  # 网络/鉴权等任何异常都不该让程序崩
            self.failed.emit(str(exc))


class IndexWorker(QObject):
    """Indexes pages into the vector store off the main thread (companion mode
    indexes pages as they're read). Failures stay silent — indexing is best
    effort and shouldn't interrupt reading."""

    done = Signal()
    failed = Signal(str)

    def __init__(self, rag, document_id, pages):
        super().__init__()
        self._rag = rag
        self._document_id = document_id
        self._pages = pages  # list[(page_number, text)]

    def run(self):
        try:
            for page_number, text in self._pages:
                self._rag.index_page(self._document_id, page_number, text)
            self.done.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
