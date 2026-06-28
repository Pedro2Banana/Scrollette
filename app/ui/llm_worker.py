from PySide6.QtCore import QObject, Signal

from app.agent.loop import run_agent
from app.agent.tools import build_registry


class AskWorker(QObject):
    """Produces one answer off the main thread: build the tool registry for the
    current reading context, then run the agent loop (it decides which tools to
    call). All network work lives here so the UI never freezes."""

    chunk = Signal(str)     # 本版非流式：整段回复一次性发出
    finished = Signal()
    failed = Signal(str)

    def __init__(
        self,
        client,
        conversation,
        page_text,
        question,
        rag,
        store,
        text_reader,
        document_id,
        max_read_page,
        today,
    ):
        super().__init__()
        self._client = client
        self._conversation = conversation
        self._page_text = page_text
        self._question = question
        self._rag = rag
        self._store = store
        self._text_reader = text_reader
        self._document_id = document_id
        self._max_read_page = max_read_page
        self._today = today

    def run(self):
        try:
            registry = build_registry(
                self._rag,
                self._store,
                self._text_reader,
                self._client,
                self._document_id,
                self._max_read_page,
            )
            messages = self._conversation.build_request(
                self._page_text, self._question, self._today
            )
            answer = run_agent(self._client, registry, messages)
            self.chunk.emit(answer)
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
