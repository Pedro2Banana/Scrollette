from app.agent.tool import Tool


class SearchBookTool(Tool):
    name = "search_book"
    description = (
        "在用户已经读过的页面里，按语义检索与问题最相关的原文片段。"
        "当需要书中的具体内容来回答时使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要检索的问题或关键词"}
        },
        "required": ["query"],
    }

    def __init__(self, rag, document_id, max_read_page):
        self._rag = rag
        self._document_id = document_id
        self._max_read_page = max_read_page

    def execute(self, query):
        hits = self._rag.retrieve(query, self._document_id, self._max_read_page)
        if not hits:
            return "（已读范围内没有检索到相关内容）"
        return "\n\n".join(f"[第{h['page_number']}页] {h['text']}" for h in hits)
