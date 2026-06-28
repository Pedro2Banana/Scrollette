from app.config import RAG_TOP_K


class Retriever:
    """Retrieve relevant chunks for a query. Qt-free.

    companion 模式：传入 ``max_read_page``，只检索已读页；
    full_book 模式：``max_read_page=None``，不限页（v1 才会用到）。
    """

    def __init__(self, embedder, store):
        self._embedder = embedder
        self._store = store

    def retrieve(self, query, document_id, max_read_page=None, page_numbers=None, k=RAG_TOP_K):
        where = self._build_where(document_id, max_read_page, page_numbers)
        vector = self._embedder.embed_one(query)
        return self._store.query(vector, k=k, where=where)

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
