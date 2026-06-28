from app.agent.tool import ToolRegistry
from app.agent.tools.content_tools import GetPagesTextTool
from app.agent.tools.rag_tools import SearchBookTool
from app.agent.tools.reading_tools import PagesReadOnTool, ReadingProgressTool
from app.agent.tools.summary_tools import SummarizeTool


def build_registry(rag, store, text_reader, client, document_id, max_read_page):
    """Build a tool registry bound to the current reading context. Rebuilt per
    question so document_id / max_read_page are always current."""
    registry = ToolRegistry()
    if rag is not None:  # RAG 不可用时退化为只有阅读记录工具
        registry.add(SearchBookTool(rag, document_id, max_read_page))
    registry.add(ReadingProgressTool(store, document_id))
    registry.add(PagesReadOnTool(store, document_id))
    registry.add(GetPagesTextTool(text_reader))
    registry.add(SummarizeTool(client, text_reader))
    return registry
