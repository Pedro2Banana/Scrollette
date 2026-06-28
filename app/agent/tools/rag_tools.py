from app.agent.tool import Tool


class SearchBookTool(Tool):
    name = "search_book"
    description = (
        "按语义检索与问题最相关的原文片段。默认在用户全部已读页里检索；"
        "若传入 page_numbers，则只在这些页里检索（用于“某天/某范围读的内容里…”）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要检索的问题或关键词"},
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "可选：只在这些页码（从1开始）里检索；不传则在全部已读页里检索",
            },
        },
        "required": ["query"],
    }

    def __init__(self, rag, document_id, max_read_page):
        self._rag = rag
        self._document_id = document_id
        self._max_read_page = max_read_page

    def execute(self, query, page_numbers=None):
        hits = self._rag.retrieve(
            query, self._document_id, self._max_read_page, page_numbers=page_numbers
        )
        if not hits:
            return "（检索范围内没有找到相关内容）"
        return "\n\n".join(f"[第{h['page_number']}页] {h['text']}" for h in hits)
