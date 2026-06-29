from app.config import RAG_TOP_K
from app.rag.fusion import reciprocal_rank_fusion


class Retriever:
    """Hybrid retrieval: semantic (vector) + lexical (BM25), fused with RRF.

    Composes three independent pieces — store.query (semantic), the BM25
    LexicalIndex (lexical), and reciprocal_rank_fusion — so each is usable on
    its own. Scope: ``page_numbers`` (explicit) > ``max_read_page`` (companion)
    > all. Qt-free.
    """

    def __init__(self, embedder, store, lexical, weights=None):
        self._embedder = embedder
        self._store = store
        self._lexical = lexical
        self._weights = weights  # [语义, 词法]，None=等权

    def retrieve(self, query, document_id, max_read_page=None, page_numbers=None, k=RAG_TOP_K):
        candidates = max(k * 2, 10)  # 每路多取些候选，融合更稳
        in_scope = self._scope_predicate(max_read_page, page_numbers)

        # 语义：向量检索（Chroma 直接按范围过滤）
        where = self._build_where(document_id, max_read_page, page_numbers)
        vector = self._embedder.embed_one(query)
        semantic = self._store.query(vector, k=candidates, where=where)

        # 词法：BM25 排整本，再按同样的范围筛
        lexical_all = self._lexical.ranked(document_id, query)
        lexical = [c for c in lexical_all if in_scope(c["page_number"])][:candidates]

        # RRF 融合两路排名（对齐用 chunk id）
        fused_ids = reciprocal_rank_fusion(
            [[h["id"] for h in semantic], [h["id"] for h in lexical]],
            weights=self._weights,
        )[:k]

        by_id = {h["id"]: h for h in lexical}
        by_id.update({h["id"]: h for h in semantic})  # 语义结果带 distance，优先
        return [by_id[i] for i in fused_ids if i in by_id]

    @staticmethod
    def _scope_predicate(max_read_page, page_numbers):
        if page_numbers:
            allowed = set(page_numbers)
            return lambda p: p in allowed
        if max_read_page is None:
            return lambda p: True
        return lambda p: p <= max_read_page

    @staticmethod
    def _build_where(document_id, max_read_page, page_numbers=None):
        # 显式页码集合优先；其次按已读范围；都没有则全文。
        if page_numbers:
            return {
                "$and": [
                    {"document_id": document_id},
                    {"page_number": {"$in": list(page_numbers)}},
                ]
            }
        if max_read_page is None:
            return {"document_id": document_id}
        return {
            "$and": [
                {"document_id": document_id},
                {"page_number": {"$lte": max_read_page}},
            ]
        }
