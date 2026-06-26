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

    def build_request(self, page_text, question):
        """Messages to send for this turn: system + recent history + the new
        question (which alone carries the current page as context)."""
        current = {
            "role": "user",
            "content": f"【当前页内容】\n{page_text}\n\n【我的问题】\n{question}",
        }
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
