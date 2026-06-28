import json
import logging

logger = logging.getLogger(__name__)


def run_agent(client, registry, messages, max_steps=5):
    """Tool-calling loop (ReAct-style): ask the model with the available tools;
    run any tool calls it requests and feed the results back; repeat until it
    returns a plain answer or we hit max_steps.

    Returns the final answer string. Synchronous — runs in the worker thread.
    """
    messages = list(messages)
    for step in range(1, max_steps + 1):
        msg = client.chat(messages, tools=registry.schemas())
        if not msg.tool_calls:
            logger.info("第%d步：直接回答（未用工具）", step)
            return msg.content or ""

        logger.info(
            "第%d步：模型决定调用 %s",
            step,
            [tc.function.name for tc in msg.tool_calls],
        )
        # 把模型这条“要调工具”的消息原样接回历史
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
        # 逐个执行，结果以 tool 角色喂回
        for tc in msg.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            logger.debug("  调用 %s(%s)", tc.function.name, arguments)
            result = registry.call(tc.function.name, arguments)
            logger.debug("  %s 返回: %s", tc.function.name, str(result)[:150])
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    # 超过步数：去掉 tools 逼模型直接给个答复收口
    logger.info("达到最大步数 %d，强制收口", max_steps)
    final = client.chat(messages)
    return final.content or "（未能在限定步数内得出答案）"
