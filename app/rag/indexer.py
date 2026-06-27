from app.rag.chunker import chunk_page


class Indexer:
    """Index document pages into the vector store. Qt-free.

    Takes plain text (not a PDF object), so it stays decoupled from the reader.
    Skips pages already indexed, so re-reading never re-embeds.
    """

    def __init__(self, embedder, store):
        self._embedder = embedder
        self._store = store

    def index_page(self, document_id, page_number, text):
        """Chunk + embed + store one page. Returns how many chunks were added
        (0 if the page was already indexed or had no text)."""
        if self._store.has_page(document_id, page_number):
            return 0
        chunks = chunk_page(text, page_number)
        if not chunks:
            return 0
        vectors = self._embedder.embed([c.text for c in chunks])
        self._store.upsert(chunks, vectors, document_id)
        return len(chunks)
