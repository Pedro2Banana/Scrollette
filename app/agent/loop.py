import json
import logging

logger = logging.getLogger(__name__)


def _snippet(text, limit=80):
    """压成单行并截断，便于在控制台一行看完。"""
    s = " ".join((text or "").split())
    return s[:limit] + ("…" if len(s) > limit else "")


def _fmt_args(args):
    return ", ".join(f"{k}={_snippet(str(v), 40)}" for k, v in args.items())


def run_agent(client, registry, messages, max_steps=5):
    """Tool-calling loop (ReAct-style): ask the model with the available tools;
    run any tool calls and feed results back; repeat until it returns a plain
    answer or we hit max_steps. Logs each step (思考/调用/返回/回答) for debugging.
    Returns the final answer string. Synchronous — runs in the worker thread.
    """
    messages = list(messages)
    for step in range(1, max_steps + 1):
        msg = client.chat(messages, tools=registry.schemas())

        if not msg.tool_calls:
            logger.info("第%d步 · 回答：%s", step, _snippet(msg.content))
            return msg.content or ""

        # 模型在调用工具前往往会带一段推理文本，作为“思考”打出来。
        if msg.content and msg.content.strip():
            logger.info("第%d步 · 思考：%s", step, _snippet(msg.content))

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            logger.info("第%d步 · 调用 %s(%s)", step, tc.function.name, _fmt_args(arguments))
            result = registry.call(tc.function.name, arguments)
            logger.info("第%d步 ·   ↳ %s 返回：%s", step, tc.function.name, _snippet(str(result)))
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    logger.info("达到最大步数 %d，强制收口作答", max_steps)
    final = client.chat(messages)
    return final.content or "（未能在限定步数内得出答案）"
