from PySide6.QtCore import QObject, Signal

from app.agent.loop import run_agent
from app.agent.router import classify
from app.agent.tools import build_registry
from app.prompts import GENERAL_PROMPT


class AskWorker(QObject):
    """Produces one answer off the main thread: route the message (book vs
    general), then run the matching handler. All network work lives here so the
    UI never freezes."""

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
        book_name,
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
        self._book_name = book_name

    def run(self):
        try:
            intent = classify(self._client, self._question, self._book_name)
            answer = (
                self._answer_general() if intent == "general" else self._answer_book()
            )
            self.chunk.emit(answer)
            self.finished.emit()
        except Exception as exc:  # 网络/鉴权等任何异常都不该让程序崩
            self.failed.emit(str(exc))

    def _answer_book(self):
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
        return run_agent(self._client, registry, messages)

    def _answer_general(self):
        # 闲聊 / 书外常识：用自身知识答，复用对话历史，不走 RAG、不带当前页。
        messages = [
            {"role": "system", "content": GENERAL_PROMPT},
            *self._conversation.history(),
            {"role": "user", "content": self._question},
        ]
        return self._client.chat(messages).content or ""


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
