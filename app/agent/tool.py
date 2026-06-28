class Tool:
    """Base class for an agent tool. Subclasses set ``name`` / ``description`` /
    ``parameters`` (JSON Schema) and implement ``execute``. Qt-free, synchronous
    (the agent loop runs in a worker thread, not asyncio)."""

    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> str:
        raise NotImplementedError

    def to_schema(self) -> dict:
        """OpenAI/Qwen function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Collects tools; hands the LLM their schemas and dispatches calls by name.

    No pre-validation — if the model sends a bad name or bad args, we return an
    error string so it can self-correct on the next loop iteration.
    """

    def __init__(self):
        self._tools = {}

    def add(self, tool):
        self._tools[tool.name] = tool

    def schemas(self):
        return [tool.to_schema() for tool in self._tools.values()]

    def call(self, name, arguments):
        tool = self._tools.get(name)
        if tool is None:
            return f"未知工具：{name}"
        try:
            return tool.execute(**arguments)
        except Exception as exc:
            return f"工具 {name} 执行出错：{exc}"
