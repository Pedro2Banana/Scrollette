import os

from openai import OpenAI

from app.config import EMBED_BATCH, EMBED_MODEL, LLM_API_KEY_ENV, LLM_BASE_URL


class Embedder:
    """Turn text into vectors via DashScope's OpenAI-compatible embeddings.

    UI-agnostic; shares the same key/endpoint as the chat LLM. Batches long
    inputs to stay under the per-request limit.
    """

    def __init__(self, api_key=None, base_url=LLM_BASE_URL, model=EMBED_MODEL):
        api_key = api_key or os.getenv(LLM_API_KEY_ENV)
        if not api_key:
            raise RuntimeError(f"未设置环境变量 {LLM_API_KEY_ENV}")
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, texts):
        """texts: list[str] -> list[list[float]] (one vector per input)."""
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            response = self._client.embeddings.create(model=self._model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def embed_one(self, text):
        return self.embed([text])[0]
