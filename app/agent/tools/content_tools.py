from app.agent.tool import Tool

PAGES_TEXT_CAP = 15  # 一次最多取多少页原文，避免塞爆上下文


class GetPagesTextTool(Tool):
    name = "get_pages_text"
    description = (
        "获取指定页码的原文（干净正文，不含批注）。"
        "当需要看某些页的具体原话、原始内容时使用。一次最多取若干页。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "要取的页码列表（从 1 开始）",
            }
        },
        "required": ["page_numbers"],
    }

    def __init__(self, reader):
        self._reader = reader  # 一个独立的 PdfDocument 句柄（办法B）

    def execute(self, page_numbers):
        if not self._reader.is_open:
            return "（当前没有打开的文档）"
        count = self._reader.page_count
        pages = sorted({p for p in page_numbers if 1 <= p <= count})  # 去重+限范围
        if not pages:
            return "（没有有效的页码）"
        if len(pages) > PAGES_TEXT_CAP:
            return f"一次最多取 {PAGES_TEXT_CAP} 页（你请求了 {len(pages)} 页），请缩小范围或改用总结。"
        parts = [f"【第{p}页】\n{self._reader.page_text(p - 1)}" for p in pages]
        return "\n\n".join(parts)
