from app.agent.tool import Tool


class SearchBookTool(Tool):
    name = "search_book"
    description = (
        "按语义+关键词混合检索书中内容。默认在当前这本书里检索；"
        "传入 book（书名）可在指定的某本已读书里检索（跨书/比较时，先用 list_read_books 看书名）；"
        "传入 page_numbers 可只在某些页里检索。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要检索的问题或关键词"},
            "book": {
                "type": "string",
                "description": "可选：在哪本已读书里检索（书名，来自 list_read_books）；不传=当前这本",
            },
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "可选：只在这些页码（从1开始）里检索",
            },
        },
        "required": ["query"],
    }

    def __init__(self, rag, store, document_id, max_read_page):
        self._rag = rag
        self._store = store
        self._document_id = document_id
        self._max_read_page = max_read_page

    def execute(self, query, book=None, page_numbers=None):
        doc_id = self._document_id
        max_read = self._max_read_page
        label = ""
        if book:
            resolved = self._store.document_id_by_name(book)
            if not resolved:
                return f"没有找到名为《{book}》的已读书；可用 list_read_books 查看书名。"
            doc_id = resolved
            label = f"《{book}》"
            if doc_id != self._document_id:
                max_read = None  # 别的书：搜它全部已索引（已读）内容
        hits = self._rag.retrieve(query, doc_id, max_read, page_numbers=page_numbers)
        if not hits:
            return "（检索范围内没有找到相关内容）"
        return "\n\n".join(f"[{label}第{h['page_number']}页] {h['text']}" for h in hits)


class ListReadBooksTool(Tool):
    name = "list_read_books"
    description = (
        "列出用户读过的所有书（书名）。当需要跨书检索、比较不同的书、"
        "或不确定某内容在哪本书时，先用它看有哪些书可选。"
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, store):
        self._store = store

    def execute(self):
        docs = self._store.list_documents()
        if not docs:
            return "（还没有读过任何书）"
        return "已读过的书：\n" + "\n".join(
            f"- {d['file_name']}（{d['page_count']}页）" for d in docs
        )
