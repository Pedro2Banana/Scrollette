class Conversation:
    """The agent's short-term memory: a managed list of dialogue turns.

    UI-agnostic. Two ideas are baked in on purpose:

    1. Durable memory vs. per-turn context — history stores only the plain
       question/answer dialogue; the bulky current-page text is attached only
       to the latest question (in ``build_request``), never kept in history.
    2. A bounded context window — only the most recent ``max_turns`` turns are
       kept (sliding window). Later this is where summarization would go.
    """

    def __init__(self, system_prompt, max_turns=10):
        self._system = system_prompt
        self._max_turns = max_turns  # 保留最近多少轮（1 轮 = 1 问 + 1 答）
        self._turns = []  # [{"role": "user"/"assistant", "content": str}, ...]

    def build_request(self, page_text, question, chunks=None):
        """Messages to send for this turn: system + recent history + the new
        question. The current page and any retrieved chunks ride along as
        per-turn context here, but never get stored in history (see record)."""
        parts = []
        if chunks:
            refs = "\n\n".join(
                f"[第{c['page_number']}页] {c['text']}" for c in chunks
            )
            parts.append(f"【相关资料（来自你读过的页）】\n{refs}")
        parts.append(f"【当前页内容】\n{page_text}")
        parts.append(f"【我的问题】\n{question}")
        current = {"role": "user", "content": "\n\n".join(parts)}
        return [{"role": "system", "content": self._system}, *self._turns, current]

    def record(self, question, answer):
        """Commit a finished turn to memory. Stores the *plain* question (no page
        context) to keep history small, then trims to the window."""
        self._turns.append({"role": "user", "content": question})
        self._turns.append({"role": "assistant", "content": answer})
        self._trim()

    def _trim(self):
        limit = self._max_turns * 2  # user + assistant 成对
        if len(self._turns) > limit:
            self._turns = self._turns[-limit:]

    def clear(self):
        self._turns = []
