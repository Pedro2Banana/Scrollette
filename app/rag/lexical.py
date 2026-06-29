import jieba
from rank_bm25 import BM25Okapi


def _tokenize(text):
    return [t for t in jieba.lcut(text) if t.strip()]


def rank_by_bm25(query, chunks):
    """Rank chunks by BM25 lexical relevance to the query.

    chunks: list of dicts each with 'id' and 'text'. Returns ids best-first.
    Builds the BM25 index over the given chunks each call (corpus is the
    in-scope chunks, so it's small); Chinese is tokenized with jieba.
    """
    if not chunks:
        return []
    corpus = [_tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [c["id"] for c, _ in ranked]


class LexicalIndex:
    """In-memory BM25 index over a document's chunks. Built lazily on first use
    (no API, pure CPU), cached for the session, and invalidated when new pages
    are indexed. Ranks the whole document; callers filter to their scope.
    """

    def __init__(self, store):
        self._store = store
        self._doc_id = None
        self._bm25 = None
        self._chunks = []  # 与语料对齐：{id, text, page_number}

    def _ensure(self, document_id):
        if self._bm25 is not None and self._doc_id == document_id:
            return
        self._chunks = self._store.get_chunks(document_id)
        corpus = [_tokenize(c["text"]) for c in self._chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._doc_id = document_id

    def invalidate(self):
        self._bm25 = None  # 下次检索时重建（有新页索引后调用）

    def ranked(self, document_id, query):
        """All chunks of the document ranked by BM25, best-first."""
        self._ensure(document_id)
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(self._chunks)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in order]
