# 方案：加入 Qwen 精排（rerank）+ 延迟对比

> 交给 Codex 实现。项目：Scrollette（PySide6 桌面 PDF「AI 陪读」，学 agent/RAG）。
> 铁律：所有非 UI 模块保持 **Qt-free**（`app/reader`、`app/llm`、`app/rag`、`app/storage`、`app/agent` 都不 import Qt）。
> 解释器：`C:/Users/Lenovo/anaconda3/envs/scrollette/python.exe`；离屏跑加 `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8`。
> 提交信息**不要**加 `Co-Authored-By: Claude` 署名（作者偏好）。

## 0. 总体思路
标准**二阶段检索**：混合召回（recall，粗排）→ 精排（rerank，重排 top-N 候选）。保持 Qt-free。
默认**关闭**，靠 config 开关，这样现有 app 行为不变，只有评估脚本显式开精排来做对比。

**模型选择（必须先确认这点）**：DashScope 托管的精排服务是 **`gte-rerank-v2`**（复用同一个
`DASHSCOPE_API_KEY` / 同一账号）。"Qwen3-Reranker"（0.6B/4B/8B）是**开源权重、需本地部署**，
DashScope API 上没有。先用 `gte-rerank-v2` 把链路和延迟对比跑通；将来想本地跑 Qwen3-Reranker 再换实现。
**注意：rerank 不在 OpenAI 兼容端点上**，现有的 `openai` client 用不了，得走 `dashscope` SDK 或原生 HTTP。

## 1. 依赖
```
pip install dashscope
```

## 2. `app/config.py` 新增
```python
# 精排（rerank / 重排）——二阶段检索的第二阶段
RAG_RERANK_ENABLED = False          # 默认关；app 侧要开精排时改这里
RAG_RERANK_MODEL = "gte-rerank-v2"  # DashScope 托管精排模型（复用同 key）
RAG_RERANK_CANDIDATES = 20          # 精排前从混合召回取多少候选，再重排到 top_k
```

## 3. 新文件 `app/rag/reranker.py`（Qt-free）
```python
import logging
import os
import time
from http import HTTPStatus

import dashscope

from app.config import LLM_API_KEY_ENV, RAG_RERANK_MODEL

logger = logging.getLogger(__name__)


class Reranker:
    """DashScope 精排：给 (query, 候选文本) 打相关性分并重排。复用聊天/embedding 同一个 key。"""

    def __init__(self, model=RAG_RERANK_MODEL, api_key=None):
        self._api_key = api_key or os.getenv(LLM_API_KEY_ENV)
        if not self._api_key:
            raise RuntimeError(f"未设置环境变量 {LLM_API_KEY_ENV}")
        self._model = model

    def rerank(self, query, candidates, top_k):
        """candidates: list[dict]，每个含 'text'。返回重排后的前 top_k 个 hit，
        并给每个加 'rerank_score'。精排失败则回退召回顺序，不中断检索。"""
        if not candidates:
            return []
        t0 = time.perf_counter()
        resp = dashscope.TextReRank.call(
            api_key=self._api_key,
            model=self._model,
            query=query,
            documents=[c["text"] for c in candidates],
            top_n=top_k,
            return_documents=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if resp.status_code != HTTPStatus.OK:
            logger.warning("精排失败(%s)，回退召回顺序：%s", resp.status_code, resp.message)
            return candidates[:top_k]
        reranked = []
        for r in resp.output.results:          # 每项含 index / relevance_score
            idx = r["index"] if isinstance(r, dict) else r.index
            score = r["relevance_score"] if isinstance(r, dict) else r.relevance_score
            hit = dict(candidates[idx])
            hit["rerank_score"] = score
            reranked.append(hit)
        logger.info("精排耗时 %.1f ms（候选 %d → top %d）", elapsed_ms, len(candidates), len(reranked))
        return reranked
```
> 注意：`resp.output.results` 元素可能是对象或 dict，上面已两种都兼容。模型 id 请对照当前 DashScope 文档核实。

## 4. 改 `app/rag/retriever.py`
- 构造函数加可选 `reranker=None`。
- `retrieve()` 加参数 `rerank=False`，并给**每个阶段计时**（`time.perf_counter()`）：
  - 召回候选数：`rerank` 为真时用 `max(RAG_RERANK_CANDIDATES, k)`，否则维持 `max(k*2, 10)`。
  - 现有逻辑先算出**融合后带 text 的完整排序**（融合结果里 semantic/lexical 命中都带 `text`）。
  - 取融合后前 N 个作为精排候选 → `if rerank and self._reranker: hits = self._reranker.rerank(query, candidates, k) else: hits = candidates[:k]`。
  - 三个阶段（语义 / 词法 / 融合）各自 `logger.info("xx耗时 %.1f ms", ...)`。
- **向后兼容**：默认 `rerank=False`、`reranker=None`，现有调用（RagService、agent 工具）完全不受影响。

## 5. 改 `app/rag/service.py`
- 懒构造一个 `Reranker`（无 key 或构造失败时置 None，别让 app 起不来）传给 `Retriever`。
- `retrieve()` 里把 `rerank=RAG_RERANK_ENABLED` 透传下去。锁保持不变。

## 6. 扩展 `experiments/eval_retrieval.py` —— **延迟对比的核心交付**
- 新增第 4 个模式 `hybrid_rerank`（`Retriever` 带 reranker、`rerank=True`）。
- 每条 query、每个模式用 `time.perf_counter()` 计时，收集每模式的延迟列表。
- 新增**延迟对比表**：每模式打印 `avg / p50 / p95 ms`。
- 头条对比改成 **hybrid vs hybrid_rerank**：一栏质量增益（hit-rate@k、MRR），一栏延迟代价（+多少 ms/query），让"值不值"一眼可见。
- 因为精排每条都有一次网络往返、跑得慢，加个 `--limit N`（先拿 10 条验证链路，再全量）。

延迟表示例格式：
```
=== 延迟对比 (top_k=5) ===
mode             avg(ms)   p50(ms)   p95(ms)
semantic           120       110       180
lexical              8         7        15
hybrid             130       120       190
hybrid_rerank      380       360       520     ← 多一次 rerank 往返
```

## 7. 运行
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 \
  C:/Users/Lenovo/anaconda3/envs/scrollette/python.exe experiments/eval_retrieval.py
```

## 8. 坑位清单
1. rerank **不走** OpenAI 兼容端点，用 `dashscope` SDK。
2. 模型 id `gte-rerank-v2` 需按当前文档核对。
3. `resp.output.results` 字段 `index` / `relevance_score`，对象/字典两种访问都兜住。
4. 精排失败**必须回退**召回顺序，不能让整条检索抛异常。
5. 计时统一用 `time.perf_counter()`，打印毫秒。
6. 保持 Qt-free；`RAG_RERANK_ENABLED` 默认 False，不动现有 app 行为。
7. 精排候选要已去重（融合里的 `by_id` 已按 chunk id 去重）。
8. eval 的 rerank 模式 API 调用多，注意配额，先 `--limit` 小跑。

## 9. 预期
40 条测试集对系统偏简单（纯语义 top_k=5 已到 ~0.975 hit-rate），**精排的质量增益可能很小甚至看不出**——
但**延迟差一定看得出**。目标就是拿到"多花几百毫秒换到多少质量提升"这个数字，量化精排的性价比。
