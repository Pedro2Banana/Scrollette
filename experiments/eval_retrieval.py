"""检索评估：语义 / 词法 / 混合 三种模式在测试集上的 Hit-rate@k 和 MRR 对比。

用法（项目根目录下）：
    python experiments/eval_retrieval.py

用独立的 eval_index（Chroma collection="eval"，目录 data/eval_index）索引测试集
覆盖到的页，不碰 app 真实使用的 rag_index，可重复运行、结果可复现。
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from app.config import DATA_DIR, DEFAULT_PDF, RAG_TOP_K  # noqa: E402
from app.reader.pdf_document import PdfDocument  # noqa: E402
from app.rag.embedder import Embedder  # noqa: E402
from app.rag.indexer import Indexer  # noqa: E402
from app.rag.lexical import LexicalIndex  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.vector_store import VectorStore  # noqa: E402

EVAL_SET_PATH = Path(__file__).resolve().parent / "eval_set.json"
EVAL_INDEX_DIR = DATA_DIR / "eval_index"
EVAL_COLLECTION = "eval"
TOP_KS = [3, 5, 10]


def load_eval_set():
    return json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))


def build_eval_index(document_id, max_page, embedder, store):
    """把覆盖测试集的页（1..max_page）索引进独立的 eval_index（已索引的页跳过）。"""
    pdf = PdfDocument()
    pdf.open(DEFAULT_PDF)
    indexer = Indexer(embedder, store)
    added_total = 0
    for page_number in range(1, max_page + 1):
        if store.has_page(document_id, page_number):
            continue
        text = pdf.page_text(page_number - 1)
        added = indexer.index_page(document_id, page_number, text)
        added_total += added
    pdf.close()
    print(f"索引完成：{max_page} 页范围内新增 {added_total} 个 chunk（已存在的页已跳过）。")


def top_k_pages_semantic(embedder, store, query, k):
    vector = embedder.embed_one(query)
    hits = store.query(vector, k=k)
    return hits


def top_k_pages_lexical(lexical, document_id, query, k):
    ranked = lexical.ranked(document_id, query)
    return ranked[:k]


def top_k_pages_hybrid(retriever, document_id, query, k):
    return retriever.retrieve(query, document_id, max_read_page=None, k=k)


def hit_rate(hits, expected_pages):
    pages = {h["page_number"] for h in hits}
    return 1.0 if pages & set(expected_pages) else 0.0


def mrr(hits, expected_pages):
    expected = set(expected_pages)
    for rank, hit in enumerate(hits, start=1):
        if hit["page_number"] in expected:
            return 1.0 / rank
    return 0.0


def evaluate(eval_set, document_id, embedder, store, lexical, retriever, k):
    """对每条问题跑三种模式，返回 {mode: {"overall": [...], "by_type": {type: [...]}}}"""
    modes = ("semantic", "lexical", "hybrid")
    results = {mode: {"hit": [], "mrr": [], "by_type": defaultdict(lambda: {"hit": [], "mrr": []})} for mode in modes}

    for item in eval_set:
        query = item["question"]
        expected = item["pages"]
        qtype = item["type"]

        hits_by_mode = {
            "semantic": top_k_pages_semantic(embedder, store, query, k),
            "lexical": top_k_pages_lexical(lexical, document_id, query, k),
            "hybrid": top_k_pages_hybrid(retriever, document_id, query, k),
        }

        for mode, hits in hits_by_mode.items():
            h = hit_rate(hits, expected)
            m = mrr(hits, expected)
            results[mode]["hit"].append(h)
            results[mode]["mrr"].append(m)
            results[mode]["by_type"][qtype]["hit"].append(h)
            results[mode]["by_type"][qtype]["mrr"].append(m)

    return results


def avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def print_report(results, k):
    print(f"\n=== top_k = {k} ===")
    header = f"{'mode':<10}{'hit-rate@k':>12}{'MRR':>10}"
    print(header)
    print("-" * len(header))
    for mode in ("semantic", "lexical", "hybrid"):
        r = results[mode]
        print(f"{mode:<10}{avg(r['hit']):>12.3f}{avg(r['mrr']):>10.3f}")

    semantic_hit = avg(results["semantic"]["hit"])
    hybrid_hit = avg(results["hybrid"]["hit"])
    semantic_mrr = avg(results["semantic"]["mrr"])
    hybrid_mrr = avg(results["hybrid"]["mrr"])
    print(
        f"\n混合 vs 纯语义增益：hit-rate@{k} {semantic_hit:+.3f} -> {hybrid_hit:.3f} "
        f"({hybrid_hit - semantic_hit:+.3f}); MRR {semantic_mrr:.3f} -> {hybrid_mrr:.3f} "
        f"({hybrid_mrr - semantic_mrr:+.3f})"
    )

    print("\n按 type 分组（hit-rate@k / MRR）：")
    types = sorted({t for r in results.values() for t in r["by_type"]})
    type_header = f"{'type':<12}" + "".join(f"{mode + '-hit':>14}{mode + '-mrr':>10}" for mode in ("semantic", "lexical", "hybrid"))
    print(type_header)
    for t in types:
        row = f"{t:<12}"
        for mode in ("semantic", "lexical", "hybrid"):
            bucket = results[mode]["by_type"].get(t, {"hit": [], "mrr": []})
            row += f"{avg(bucket['hit']):>14.3f}{avg(bucket['mrr']):>10.3f}"
        print(row)


def main():
    eval_set = load_eval_set()
    max_page = max(p for item in eval_set for p in item["pages"])

    pdf = PdfDocument()
    pdf.open(DEFAULT_PDF)
    document_id = pdf.file_hash
    pdf.close()

    embedder = Embedder()
    store = VectorStore(path=EVAL_INDEX_DIR, collection=EVAL_COLLECTION)
    lexical = LexicalIndex(store)
    retriever = Retriever(embedder, store, lexical)

    build_eval_index(document_id, max_page, embedder, store)

    for k in TOP_KS:
        results = evaluate(eval_set, document_id, embedder, store, lexical, retriever, k)
        print_report(results, k)


if __name__ == "__main__":
    main()
