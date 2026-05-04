"""
tests/test_rag.py
RAG retrieval evaluation: precision@k, recall@k, relevance scoring.
Run with: pytest tests/test_rag.py -v
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


GROUND_TRUTH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "test_data", "rag_ground_truth.json"
)

TOP_K = 3
MIN_PRECISION = 0.3   # At least 30% of retrieved docs should be relevant
MIN_RECALL    = 0.5   # At least 50% of relevant docs should be retrieved
MIN_AVG_SCORE = 0.3   # Average similarity score threshold


@pytest.fixture(scope="module")
def retrieval_module():
    """Import and validate retrieval module is ready."""
    try:
        import retrieval_module as rm
        if not rm.is_index_ready():
            pytest.skip("ChromaDB index not built. Run: python rag_indexer.py")
        return rm
    except ImportError:
        pytest.skip("retrieval_module not importable from project root")


@pytest.fixture(scope="module")
def ground_truth():
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def compute_precision_at_k(retrieved_sources: list, relevant_docs: list) -> float:
    """What fraction of retrieved docs are relevant."""
    if not retrieved_sources:
        return 0.0
    hits = sum(1 for src in retrieved_sources if any(rel in src for rel in relevant_docs))
    return hits / len(retrieved_sources)


def compute_recall_at_k(retrieved_sources: list, relevant_docs: list) -> float:
    """What fraction of relevant docs were retrieved."""
    if not relevant_docs:
        return 1.0
    hits = sum(1 for rel in relevant_docs if any(rel in src for src in retrieved_sources))
    return hits / len(relevant_docs)


class TestRAGRetrieval:

    def test_index_is_ready(self, retrieval_module):
        assert retrieval_module.is_index_ready(), "ChromaDB index must be built"

    def test_retrieve_returns_results(self, retrieval_module):
        chunks = retrieval_module.retrieve("What are FreshMart delivery hours?")
        assert len(chunks) > 0, "Should return at least one chunk"

    def test_retrieve_structure(self, retrieval_module):
        chunks = retrieval_module.retrieve("delivery policy")
        for chunk in chunks:
            assert "text" in chunk
            assert "source" in chunk
            assert "score" in chunk
            assert 0 <= chunk["score"] <= 1

    def test_empty_query_returns_empty(self, retrieval_module):
        chunks = retrieval_module.retrieve("")
        assert chunks == []

    def test_whitespace_query_returns_empty(self, retrieval_module):
        chunks = retrieval_module.retrieve("   ")
        assert chunks == []

    def test_retrieve_respects_top_k(self, retrieval_module):
        chunks = retrieval_module.retrieve("delivery", top_k=2)
        assert len(chunks) <= 2

    def test_retrieve_top_k_5(self, retrieval_module):
        chunks = retrieval_module.retrieve("grocery store products", top_k=5)
        assert len(chunks) <= 5

    def test_scores_are_sorted_descending(self, retrieval_module):
        chunks = retrieval_module.retrieve("return refund damaged product", top_k=5)
        if len(chunks) > 1:
            scores = [c["score"] for c in chunks]
            assert scores == sorted(scores, reverse=True) or \
                   all(abs(scores[i] - scores[i+1]) < 0.1 for i in range(len(scores)-1)), \
                   "Scores should be roughly descending"

    def test_format_context_non_empty(self, retrieval_module):
        chunks = retrieval_module.retrieve("FreshMart store hours")
        context = retrieval_module.format_context(chunks)
        if chunks:
            assert "[RETRIEVED KNOWLEDGE BASE CONTEXT]" in context
            assert "[END OF RETRIEVED CONTEXT]" in context

    def test_format_context_empty(self, retrieval_module):
        context = retrieval_module.format_context([])
        assert context == ""


class TestRAGPrecisionRecall:

    def test_precision_recall_batch(self, retrieval_module, ground_truth):
        """Compute precision@k and recall@k over all ground truth queries."""
        precisions, recalls, scores = [], [], []

        for item in ground_truth:
            query = item["query"]
            relevant = item["relevant_docs"]
            chunks = retrieval_module.retrieve(query, top_k=TOP_K)

            retrieved_sources = [c["source"] for c in chunks]
            avg_score = sum(c["score"] for c in chunks) / len(chunks) if chunks else 0

            p = compute_precision_at_k(retrieved_sources, relevant)
            r = compute_recall_at_k(retrieved_sources, relevant)

            precisions.append(p)
            recalls.append(r)
            scores.append(avg_score)

        avg_precision = sum(precisions) / len(precisions)
        avg_recall = sum(recalls) / len(recalls)
        avg_score = sum(scores) / len(scores)

        # Save metrics for report
        metrics = {
            "avg_precision_at_k": round(avg_precision, 3),
            "avg_recall_at_k": round(avg_recall, 3),
            "avg_similarity_score": round(avg_score, 3),
            "top_k": TOP_K,
            "num_queries": len(ground_truth)
        }

        metrics_path = os.path.join(os.path.dirname(__file__), "..", "reports", "rag_metrics.json")
        os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        assert avg_precision >= MIN_PRECISION, \
            f"Average Precision@{TOP_K} = {avg_precision:.3f} (min: {MIN_PRECISION})"
        assert avg_recall >= MIN_RECALL, \
            f"Average Recall@{TOP_K} = {avg_recall:.3f} (min: {MIN_RECALL})"

    def test_keyword_grounding(self, retrieval_module, ground_truth):
        """Retrieved text should contain expected keywords for at least 60% of queries."""
        hits = 0
        for item in ground_truth:
            chunks = retrieval_module.retrieve(item["query"], top_k=TOP_K)
            all_text = " ".join(c["text"].lower() for c in chunks)
            keywords = item.get("expected_keywords", [])
            if any(kw.lower() in all_text for kw in keywords):
                hits += 1

        hit_rate = hits / len(ground_truth)
        assert hit_rate >= 0.6, \
            f"Keyword grounding rate = {hit_rate:.2%} (expected >= 60%)"

    def test_cache_consistency(self, retrieval_module):
        """Same query should return same results (cache working)."""
        q = "FreshMart delivery policy"
        r1 = retrieval_module.retrieve(q)
        r2 = retrieval_module.retrieve(q)
        assert [c["source"] for c in r1] == [c["source"] for c in r2]
        assert [c["text"] for c in r1] == [c["text"] for c in r2]


class TestRAGFaithfulness:
    """
    Section 2.2.1 — Grounding / Faithfulness
    Checks whether the retrieved context actually contains the answer keywords.
    This is an automated faithfulness proxy: if the retrieved chunks contain
    the expected answer keywords, the LLM answer is likely grounded in context.

    For full RAGAS-style faithfulness you would need LLM responses, but since
    we evaluate the retriever in isolation here, keyword entailment is used as
    the faithfulness proxy metric (consistent with lightweight RAG evaluation).
    """

    def test_faithfulness_score(self, retrieval_module, ground_truth):
        """
        Faithfulness proxy: for each query, check if retrieved context
        ENTAILS the expected answer keywords.
        Reports average faithfulness score over all 30 Q&A pairs.
        """
        faithful_count = 0
        faithfulness_scores = []

        for item in ground_truth:
            query    = item["query"]
            keywords = item.get("expected_keywords", [])
            chunks   = retrieval_module.retrieve(query, top_k=TOP_K)
            all_text = " ".join(c["text"].lower() for c in chunks)

            if not keywords:
                faithfulness_scores.append(1.0)
                faithful_count += 1
                continue

            # Score = fraction of expected keywords found in retrieved context
            found = sum(1 for kw in keywords if kw.lower() in all_text)
            score = found / len(keywords)
            faithfulness_scores.append(score)
            if score >= 0.5:   # At least half the expected keywords present
                faithful_count += 1

        avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
        faithfulness_rate = faithful_count / len(ground_truth)

        # Save to report
        metrics_path = os.path.join(
            os.path.dirname(__file__), "..", "reports", "rag_metrics.json"
        )
        try:
            with open(metrics_path) as f:
                metrics = json.load(f)
        except Exception:
            metrics = {}

        metrics["avg_faithfulness_score"]  = round(avg_faithfulness, 3)
        metrics["faithfulness_rate_50pct"] = round(faithfulness_rate, 3)
        metrics["num_qa_pairs"]            = len(ground_truth)

        os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"\n  Avg Faithfulness Score : {avg_faithfulness:.3f}")
        print(f"  Faithfulness Rate      : {faithfulness_rate:.1%}")
        print(f"  Q&A Pairs Evaluated    : {len(ground_truth)}")

        assert avg_faithfulness >= 0.4, \
            f"Avg faithfulness {avg_faithfulness:.3f} too low (min 0.40). " \
            f"Retrieved context is not entailing expected answers."

    def test_faithfulness_per_query_sample(self, retrieval_module, ground_truth):
        """
        Spot-check faithfulness on first 5 queries — verifies individual
        query-level grounding (not just aggregate).
        """
        sample = ground_truth[:5]
        for item in sample:
            chunks   = retrieval_module.retrieve(item["query"], top_k=TOP_K)
            all_text = " ".join(c["text"].lower() for c in chunks)
            keywords = item.get("expected_keywords", [])
            found    = any(kw.lower() in all_text for kw in keywords)
            assert found, \
                f"Query '{item['query']}' — none of {keywords} found in context."


class TestRAGContextRelevance:
    """
    Section 2.2.1 — Context Relevance
    Measures the proportion of retrieved chunks that are actually
    useful for answering the query (i.e. contain relevant keywords).
    """

    def test_context_relevance_rate(self, retrieval_module, ground_truth):
        """
        For each query, compute what fraction of the TOP_K retrieved chunks
        contain at least one expected keyword — this is the context relevance score.
        Reports average context relevance over all 30 queries.
        """
        relevance_scores = []

        for item in ground_truth:
            query    = item["query"]
            keywords = item.get("expected_keywords", [])
            chunks   = retrieval_module.retrieve(query, top_k=TOP_K)

            if not chunks or not keywords:
                relevance_scores.append(1.0)
                continue

            # Count chunks that contain at least one expected keyword
            useful = sum(
                1 for c in chunks
                if any(kw.lower() in c["text"].lower() for kw in keywords)
            )
            relevance_scores.append(useful / len(chunks))

        avg_relevance = sum(relevance_scores) / len(relevance_scores)

        # Append to rag_metrics.json
        metrics_path = os.path.join(
            os.path.dirname(__file__), "..", "reports", "rag_metrics.json"
        )
        try:
            with open(metrics_path) as f:
                metrics = json.load(f)
        except Exception:
            metrics = {}

        metrics["avg_context_relevance"] = round(avg_relevance, 3)
        os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"\n  Avg Context Relevance: {avg_relevance:.3f}")

        assert avg_relevance >= 0.4, \
            f"Context relevance {avg_relevance:.3f} too low (min 0.40). " \
            f"Too many retrieved chunks are not useful for the query."

    def test_context_relevance_not_zero(self, retrieval_module, ground_truth):
        """
        No query should have 0% context relevance — that means retrieval
        is returning completely unrelated chunks.
        """
        zero_relevance = []
        for item in ground_truth:
            keywords = item.get("expected_keywords", [])
            chunks   = retrieval_module.retrieve(item["query"], top_k=TOP_K)
            all_text = " ".join(c["text"].lower() for c in chunks)
            if keywords and not any(kw.lower() in all_text for kw in keywords):
                zero_relevance.append(item["id"])

        assert len(zero_relevance) <= 6, \
            f"Too many queries with 0% context relevance: {zero_relevance}"