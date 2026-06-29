import logging

from app.agent.tool import Tool
from app.prompts import SUMMARY_MAP_PROMPT, SUMMARY_REDUCE_PROMPT

logger = logging.getLogger(__name__)

SUMMARIZE_PAGE_CAP = 60  # 一次最多总结多少页（防失控；整本总结属 full_book，另议）
BATCH_CHARS = 6000       # map 阶段每批的目标字数


def _summarize_text(client, text, reduce=False):
    prefix = SUMMARY_REDUCE_PROMPT if reduce else SUMMARY_MAP_PROMPT
    msg = client.chat([{"role": "user", "content": prefix + text}])
    return (msg.content or "").strip()


def summarize_pages(client, reader, page_numbers):
    """Map-reduce 总结：先把页文本按 ~BATCH_CHARS 分批、每批各自总结（map），
    再把分段小结归并（reduce）。自适应——只有一批时就一次调用、无需归并。"""
    batches, cur, cur_len = [], [], 0
    for p in page_numbers:
        piece = f"【第{p}页】\n{reader.page_text(p - 1)}"
        if cur and cur_len + len(piece) > BATCH_CHARS:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(piece)
        cur_len += len(piece)
    if cur:
        batches.append(cur)

    logger.info("summarize: %d 页 → %d 批", len(page_numbers), len(batches))
    partials = [_summarize_text(client, "\n\n".join(b)) for b in batches]  # map
    if len(partials) == 1:
        return partials[0]
    return _summarize_text(client, "\n\n".join(partials), reduce=True)      # reduce


class SummarizeTool(Tool):
    name = "summarize"
    description = (
        "总结指定页码的内容（页数多时自动分段总结再归并）。"
        "当用户要“总结某些页 / 某天读的内容 / 这几页讲了什么（要概括而非原文）”时使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "要总结的页码列表（从 1 开始）",
            }
        },
        "required": ["page_numbers"],
    }

    def __init__(self, client, reader):
        self._client = client
        self._reader = reader

    def execute(self, page_numbers):
        if not self._reader.is_open:
            return "（当前没有打开的文档）"
        count = self._reader.page_count
        pages = sorted({p for p in page_numbers if 1 <= p <= count})
        if not pages:
            return "（没有有效的页码）"
        if len(pages) > SUMMARIZE_PAGE_CAP:
            return f"页数太多（{len(pages)} 页），一次最多总结 {SUMMARIZE_PAGE_CAP} 页，请缩小范围。"
        return summarize_pages(self._client, self._reader, pages)
