import os

from openai import OpenAI

from app.config import LLM_API_KEY_ENV, LLM_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = (
    "你是一个 PDF 阅读助手，正在陪用户一起读书。你可以使用以下工具："
    "search_book（在用户读过的书中内容里检索）、"
    "get_reading_progress（查阅读进度）、"
    "pages_read_on（查某天读了哪些页）。"
    "只要问题涉及书中的概念或内容，都应先调用 search_book 检索书里的原文作为依据，"
    "再结合检索结果用简洁中文回答，而不是仅凭你自己的知识作答；"
    "涉及阅读记录（读到哪、某天读了啥）时调用对应工具。"
    "引用书中内容时标注来源页码（如“见第 7 页”）。"
    "不要编造，也不要剧透用户尚未读到的后文。"
)


class LLMClient:
    """Thin, UI-agnostic wrapper over an OpenAI-compatible chat endpoint
    (configured for Qwen / DashScope). Knows nothing about Qt or PDF."""

    def __init__(self, api_key=None, base_url=LLM_BASE_URL, model=LLM_MODEL):
        api_key = api_key or os.getenv(LLM_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(f"未设置环境变量 {LLM_API_KEY_ENV}")
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def ask(self, messages):
        """Send a full message list; return the full reply string."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        return response.choices[0].message.content

    def chat(self, messages, tools=None):
        """One non-streaming completion; returns the response message (which may
        carry tool_calls). Used by the agent loop."""
        kwargs = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message

    def ask_stream(self, messages):
        """Send a full message list; yield the reply piece by piece as it arrives."""
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
