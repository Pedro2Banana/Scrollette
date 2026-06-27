import threading

from app.rag.embedder import Embedder
from app.rag.indexer import Indexer
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorStore


class RagService:
    """One entry point bundling the RAG pieces (embedder, store, retriever,
    indexer). Qt-free; the UI holds a single instance.

    Reads (retrieve) and writes (index) arrive from different worker threads,
    so a lock serializes all vector-store access.
    """

    def __init__(self):
        embedder = Embedder()
        store = VectorStore()
        self._retriever = Retriever(embedder, store)
        self._indexer = Indexer(embedder, store)
        self._lock = threading.Lock()

    def retrieve(self, query, document_id, max_read_page):
        with self._lock:
            return self._retriever.retrieve(
                query, document_id, max_read_page=max_read_page
            )

    def index_page(self, document_id, page_number, text):
        with self._lock:
            return self._indexer.index_page(document_id, page_number, text)
