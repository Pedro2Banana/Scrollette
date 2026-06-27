import os

from openai import OpenAI

from app.config import LLM_API_KEY_ENV, LLM_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = (
    "你是一个 PDF 阅读助手，正在陪用户一起读书。"
    "请优先依据“当前页内容”和“相关资料（来自用户读过的页）”用简洁中文回答，"
    "引用资料时标注来源页码（如“见第 7 页”）。"
    "如果这些内容不足以回答，就如实说明，不要编造，也不要假设用户尚未读到的后文。"
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
