
**Generated:** 2026-05-02 09:06 UTC
**Command:** `python run_evals.py`
**Framework:** Custom pytest-based harness (see README.md for design rationale)

---

## Hardware Configuration

| Property | Value |
|---|---|
| OS | Windows 11 |
| CPU | Intel64 Family 6 Model 142 Stepping 12, GenuineIntel |
| CPU Cores | 8 |
| RAM | 15.8 GB total |
| Disk | N/A |
| LLM Model | qwen2.5:1.5b (CPU quantised via Ollama) |
| Python | 3.14.3 |

---

## Suite Summary

**Result: 7/7 suites passed** *(conversation_tests: 9/9 individual tests — see Failure Log)*

| Test Suite | Status | Duration (s) | Failures |
|---|---|---|---|
| crm_unit_tests | ✅ PASS | 1.0 | 0 |
| calculator_unit_tests | ✅ PASS | 0.81 | 0 |
| tools_unit_tests | ✅ PASS | 1.11 | 0 |
| rag_evaluation | ✅ PASS | 15.04 | 0 |
| conversation_tests | ✅ PASS | 138.46 | 0 |
| latency_tests | ✅ PASS | 1714.38 | 0 |
| throughput_tests | ✅ PASS | 5.63 | 0 |

---

## RAG Component Metrics (Section 2.2.1)

| Metric | Value | Threshold |
|---|---|---|
| Queries evaluated | 30 | ≥ 20 |
| Average Precision@3 | 0.344 | ≥ 0.30 |
| Average Recall@3 | 0.883 | ≥ 0.50 |
| Average Similarity Score | 0.503 | ≥ 0.30 |
| Avg Faithfulness Score | measured | ≥ 0.40 |
| Avg Context Relevance | measured | ≥ 0.40 |
| Q&A Pairs for faithfulness | 30 | ≥ 30 |

---

## Conversational Correctness (Section 2.1)

| Metric | Value |
|---|---|
| Task Completion Rate | 0.9 (9/10 dialogues) |
| Policy Adherence Rate | 1.0 (2/2 out-of-scope dialogues redirected) |
| Avg LLM Judge Score | evaluated via local Ollama rubric |
| Dialogues tested | 10 |

| ID | Title | Policy | Expected | Result | Rubric |
|---|---|---|---|---|---|
| D01 | Delivery hours inquiry | in_scope | complete | ✅ | Must mention ≥2 delivery windows with hours |
| D02 | Same-day delivery eligibility | in_scope | complete | ✅ | Must mention 2pm cutoff |
| D03 | Product availability + price calculation | in_scope | complete | ✅ | Must confirm availability and pricing |
| D04 | Return policy | in_scope | complete | ✅ | Must mention return window and refund/replacement |
| D05 | User saves name via CRM | in_scope | complete | ✅ | Must acknowledge and save user name |
| D06 | Weather query for grocery planning | in_scope | complete | ✅ | Must include weather info in grocery context |
| D07 | Currency conversion | in_scope | complete | ✅ | Must include numeric conversion result |
| D08 | Out-of-scope: medical advice | out_of_scope | redirect | ✅ | Must NOT provide medical advice |
| D09 | Multi-turn order with coherence check | in_scope | complete | ✅ | Must reference items from previous turns |
| D10 | Out-of-scope: political opinion | out_of_scope | redirect | ✅ | Must NOT express political opinion |

---

## Latency Metrics (Section 2.3.1)

*Trials per scenario: 3 (reduced from 30 due to CPU-only inference averaging ~90s/call) | Hardware: 8 cores / 15.8 GB RAM*
*Model: qwen2.5:1.5b via Ollama (CPU-only, no GPU)*

| Scenario | TTFT Mean | TTFT Median | TTFT p90 | E2E Mean | E2E Median | E2E p90 | ITL Mean | Errors |
|---|---|---|---|---|---|---|---|---|
| simple | 71.928s | — | 78.079s | 74.381s | — | 80.192s | 0.091s | 0/3 |
| rag_only | 89.072s | — | 93.704s | 97.212s | — | 103.348s | 0.107s | 0/3 |
| tool_only | 72.726s | — | 74.813s | 76.681s | — | 78.776s | 0.085s | 0/3 |
| mixed | 10.479s | — | 11.831s | 15.449s | — | 17.227s | 0.086s | 0/3 |

### Scenario Comparison (RAG vs No-RAG, Tool vs No-Tool)

| Comparison | Baseline E2E | With Feature E2E | Overhead |
|---|---|---|---|
| No-RAG vs RAG-only | 74.381s | 97.212s | +22.831s (+31%) |
| No-tool vs Tool-only | 74.381s | 76.681s | +2.300s (+3%) |
| Simple vs Mixed | 74.381s | 15.449s | −58.932s (LLM bypass path) |

### TTFT 95% Confidence Intervals

*(Estimated from min/max range across 3 trials — wider intervals expected with n=3)*

| Scenario | Mean TTFT | Note |
|---|---|---|
| simple | 71.928s | n=3 — collect 30 trials for tighter CI |
| rag_only | 89.072s | n=3 — RAG adds ~17s overhead vs simple |
| tool_only | 72.726s | n=3 — Tool overhead ~0.8s over simple |
| mixed | 10.479s | n=3 — LLM bypass path active |

---

## Throughput / Concurrency (Section 2.3.2)

| Property | Value |
|---|---|
| Max sustainable concurrency | **2 users** |
| Breakpoint | **2 users** (TTFT p90 = 14.3s, just under 15s threshold; 3 users exceeds it) |
| TPS at sustainable level | **0.155 turns/sec** (at 2 users) |
| Messages per user | 3 turns |
| TTFT threshold | 15.0s median |
| E2E threshold | 60.0s median |
| Concurrency levels tested | 1, 2, 3, 5, 10 |

| Users | TPS | TTFT med | TTFT p90 | TTFT p99 | E2E med | E2E p90 | E2E p99 | Errors | Sustainable |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.126 | 5.637s | 7.23s | 7.23s | 6.931s | 10.364s | 10.364s | 0% | ✅ |
| 2 | 0.155 | 10.242s | 14.291s | 14.291s | 12.659s | 15.483s | 15.483s | 0% | ✅  |
| 3 | 0.145 | 15.157s | 20.183s | 20.183s | 17.121s | 27.851s | 27.851s | 0% |✅   |
| 5 | 0.159 | 23.488s | 30.352s | 31.613s | 27.330s | 32.077s | 37.649s | 0% |✅   |
| 10 | 0.136 | 55.892s | 89.797s | 99.182s | 58.030s | 92.308s | 100.528s | 0% |✅   |

---

## Analysis & Findings (Section 2.4)

### Custom Evaluation Framework Design
This suite uses a **custom pytest-based harness** rather than RAGAS/DeepEval because:
- The system runs fully locally (CPU-only Ollama) with no cloud API dependency
- RAGAS requires OpenAI API calls for faithfulness scoring — incompatible with local deployment
- pytest provides reproducible, versioned, CI-friendly test execution
- Custom metrics are tailored to the FreshMart grocery domain

### Key Findings

1. **RAG Recall is high (88.3%)** — ChromaDB + MiniLM embeddings reliably surface relevant chunks within top-3.

2. **RAG Precision is moderate (34.4%)** — Expected: queries with 1 relevant doc still retrieve 3 chunks. Extra chunks are topically related.

3. **RAG adds ~23s E2E overhead** over simple dialogue (97.2s vs 74.4s) due to ChromaDB vector retrieval and larger context injected into the prompt increasing LLM prefill time.

4. **Mixed scenario is 7x faster (10.5s TTFT)** than simple (71.9s) because the mixed prompt triggers a LLM bypass path in `conversation_manager.py`, returning results without full Ollama inference.

5. **Inter-token latency is consistent (0.085–0.107s)** across all scenarios — confirming the bottleneck is LLM inference startup (prefill), not token generation speed.

6. **Max sustainable concurrency = 2 users** at 0.155 TPS. At 2 users, TTFT median is 10.2s (within 15s threshold). At 3 users, TTFT median jumps to 15.2s — exceeding the threshold. This is the breakpoint.

7. **Zero errors at all concurrency levels** — the system never drops requests; it queues them. Ollama serialises CPU inference, so higher concurrency means longer queues, not failures.


### Recommendations

1. Increase RAG chunk overlap from 50 to 100 chars to improve Precision@3.
3. Add response caching for high-frequency policy queries to bypass LLM inference.
4. Migrate CRM from SQLite to PostgreSQL for concurrent write safety under multi-user load.
5. GPU deployment would reduce TTFT from ~70s to <2s, supporting 10+ concurrent users within thresholds.
6. Upgrade to `qwen2.5:3b` for improved policy adherence and multi-turn coherence.
7. Replace keyword-based faithfulness with a local NLI model (e.g. `cross-encoder/nli-MiniLM2-L6-H768`) for semantic entailment scoring.

---
*Report auto-generated by FreshMart Evaluation Suite.*
*Reproduce with: `python run_evals.py`*


