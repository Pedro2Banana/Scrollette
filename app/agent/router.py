import logging

from app.prompts import ROUTER_PROMPT

logger = logging.getLogger(__name__)


def classify(client, message, book_name):
    """Route one message to a handler: 'book'（关于当前这本书）或
    'general'（闲聊 / 书外常识 / 别的书）。一次轻量 LLM 分类调用，
    拿不准时默认 'book'（工具更全、还能兜底）。"""
    prompt = ROUTER_PROMPT.format(book=book_name or "当前文档")
    raw = (
        client.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ]
        ).content
        or ""
    ).strip().lower()
    intent = "general" if "general" in raw else "book"
    logger.info("路由 → %s（模型输出 %r）", intent, raw[:20])
    return intent
