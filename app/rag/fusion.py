def reciprocal_rank_fusion(ranked_lists, weights=None, k=60):
    """Reciprocal Rank Fusion: merge several ranked id-lists into one ranking.

    Each id's score is the weighted sum over the lists it appears in of
    weight / (k + rank), rank starting at 1. Only ranks matter (no need to
    normalize the retrievers' raw scores). `weights` lets you tune each list's
    influence (e.g. boost BM25 for keyword-y queries); defaults to equal.
    Returns ids sorted best-first.
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    scores = {}
    for ranked, weight in zip(ranked_lists, weights):
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
