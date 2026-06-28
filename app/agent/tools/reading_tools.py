from app.agent.tool import Tool


class ReadingProgressTool(Tool):
    name = "get_reading_progress"
    description = (
        "查询用户当前这本书的阅读进度：读过多少页、最远读到第几页。"
        "当用户问“我读到哪了 / 读了多少”时使用。"
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, store, document_id):
        self._store = store
        self._document_id = document_id

    def execute(self):
        p = self._store.reading_progress(self._document_id)
        return f"已读 {p['pages_read']} 页，最远读到第 {p['max_read_page']} 页。"


class PagesReadOnTool(Tool):
    name = "pages_read_on"
    description = (
        "查询用户在某一天读了哪些页。日期用 YYYY-MM-DD 格式。"
        "当用户问“我某天/今天/昨天读了哪些”时使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"}
        },
        "required": ["date"],
    }

    def __init__(self, store, document_id):
        self._store = store
        self._document_id = document_id

    def execute(self, date):
        pages = self._store.pages_read_on(self._document_id, date)
        if not pages:
            return f"{date} 没有阅读记录。"
        return f"{date} 读了第 {', '.join(map(str, pages))} 页。"
