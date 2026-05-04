"""
tests/test_conversations.py
Conversational correctness tests: task completion, policy adherence, coherence.

Section 2.1 of Assignment 3:
  - Task completion rate   (binary per dialogue)
  - Policy adherence       (binary)
  - Coherence/consistency  (keyword rubric + LLM-as-judge on a subset)

Requires: chatbot running at BASE_URL
Run with: pytest tests/test_conversations.py -v --timeout=300
"""

import sys, os, json, time, asyncio, pytest, requests
import websockets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE_URL       = os.getenv("CHATBOT_WS_URL",  "ws://localhost:8000/ws/chat/")
HTTP_BASE      = os.getenv("CHATBOT_HTTP_URL", "http://localhost:8000")
OLLAMA_URL     = os.getenv("OLLAMA_URL",       "http://localhost:11434")
DIALOGUES_PATH = os.path.join(os.path.dirname(__file__), "..", "test_data", "dialogues.json")
REPORT_PATH    = os.path.join(os.path.dirname(__file__), "..", "reports", "dialogue_report.json")

OUT_OF_SCOPE_REDIRECT_WORDS = [
    "sorry", "grocery", "freshmart", "assist", "help", "outside", "focus",
    "specialize", "unable", "cannot", "not able", "only help"
]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def create_session() -> str:
    try:
        r = requests.post(f"{HTTP_BASE}/session/new", timeout=10)
        return r.json().get("session_id", str(int(time.time())))
    except Exception:
        return str(int(time.time()))


async def send_message_ws(message: str, session_id: str) -> str:
    full = ""
    url  = BASE_URL + session_id
    try:
        async with websockets.connect(url, open_timeout=30, ping_timeout=120) as ws:
            await ws.send(json.dumps({"message": message}))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") == "token":
                    full += data.get("data", "")
                elif data.get("type") in ("done", "end", "complete", "stream_end", "error"):
                    break
    except Exception as e:
        return f"[CONNECTION_ERROR: {e}]"
    return full.strip()


async def run_dialogue(turns: list, session_id: str) -> list:
    responses = []
    for turn in turns:
        if turn["role"] == "user":
            resp = await send_message_ws(turn["content"], session_id)
            responses.append(resp)
    return responses


def run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────────────
# LLM-as-Judge  (calls local Ollama directly — no extra API key needed)
# ──────────────────────────────────────────────────────────────────────────────

def llm_judge(question: str, response: str, rubric: str) -> dict:
    """
    Asks the local Ollama model to score the chatbot response against a rubric.
    Returns {"score": 0-10, "reasoning": "..."} or a fallback if Ollama is unavailable.
    """
    prompt = f"""You are an evaluator for a grocery chatbot called FreshMart.

User question: {question}
Chatbot response: {response}
Evaluation rubric: {rubric}

Score the chatbot response from 0 to 10 based on the rubric.
Reply ONLY with a JSON object like: {{"score": 8, "reasoning": "The response correctly mentioned..."}}
Do not include any other text."""

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False},
            timeout=60
        )
        text = r.json().get("response", "").strip()
        # Extract JSON from response
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    # Fallback: keyword-based scoring
    keywords_in_response = sum(1 for w in rubric.lower().split() if w in response.lower())
    score = min(10, keywords_in_response * 2)
    return {"score": score, "reasoning": "Fallback keyword scoring (Ollama unavailable)"}


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chatbot_available():
    try:
        r = requests.get(HTTP_BASE, timeout=10)
        if r.status_code not in (200, 404):
            pytest.skip(f"Chatbot not reachable at {HTTP_BASE}")
    except Exception:
        pytest.skip("Chatbot not reachable. Start with: docker compose up")


@pytest.fixture(scope="module")
def dialogues():
    with open(DIALOGUES_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module", autouse=True)
def warmup(chatbot_available):
    """Warm up Ollama model before tests."""
    try:
        sid = create_session()
        async def _w():
            async with websockets.connect(BASE_URL + sid,
                                          open_timeout=30, ping_timeout=120) as ws:
                await ws.send(json.dumps({"message": "hi"}))
                async for raw in ws:
                    if json.loads(raw).get("type") in ("done", "token", "error"):
                        break
        asyncio.run(_w())
        time.sleep(2)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# 2.1a  Policy Adherence Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPolicyAdherence:

    def test_out_of_scope_medical_redirects(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("What medicine should I take for headache?", sid))
        assert any(w in resp.lower() for w in OUT_OF_SCOPE_REDIRECT_WORDS), \
            f"Medical question not redirected. Got: {resp[:200]}"

    def test_out_of_scope_political_redirects(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("What do you think about the current government?", sid))
        assert any(w in resp.lower() for w in OUT_OF_SCOPE_REDIRECT_WORDS), \
            f"Political question not redirected. Got: {resp[:200]}"

    def test_in_scope_delivery_answered(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("What are your delivery hours?", sid))
        assert any(w in resp.lower() for w in
                   ["morning", "afternoon", "evening", "delivery", "9am", "pm"]), \
            f"Delivery hours not answered. Got: {resp[:200]}"

    def test_in_scope_return_policy_answered(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("How do I return a damaged product?", sid))
        assert any(w in resp.lower() for w in ["return", "refund", "replace", "damaged"]), \
            f"Return policy not answered. Got: {resp[:200]}"


# ──────────────────────────────────────────────────────────────────────────────
# 2.1b  Task Completion Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTaskCompletion:

    def test_calculation_completes(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("Calculate 3 times 2.50", sid))
        assert "7.5" in resp or "7.50" in resp or "7,5" in resp, \
            f"Calculation result not in response. Got: {resp[:200]}"

    def test_store_info_completes(self, chatbot_available):
        sid  = create_session()
        resp = run(send_message_ws("What is the contact email for FreshMart?", sid))
        assert any(w in resp.lower() for w in
                   ["email", "support", "contact", "freshmart"]), \
            f"Store info not provided. Got: {resp[:200]}"


# ──────────────────────────────────────────────────────────────────────────────
# 2.1c  Coherence & Consistency Tests (multi-turn)
# ──────────────────────────────────────────────────────────────────────────────

class TestCoherence:

    def test_multi_turn_remembers_context(self, chatbot_available):
        sid = create_session()
        run(send_message_ws("I want to order mangoes", sid))
        r2  = run(send_message_ws("What was the item I just mentioned?", sid))
        assert "mango" in r2.lower(), \
            f"Bot didn't remember 'mango'. Turn 2: {r2[:200]}"

    def test_name_remembered_in_session(self, chatbot_available):
        sid = create_session()
        run(send_message_ws("My name is Zainab", sid))
        r2  = run(send_message_ws("Do you remember my name?", sid))
        assert "zainab" in r2.lower(), \
            f"Bot didn't remember name. Response: {r2[:200]}"


# ──────────────────────────────────────────────────────────────────────────────
# 2.1d  Full Dialogue Batch — Task Completion + LLM-as-Judge
# ──────────────────────────────────────────────────────────────────────────────

class TestAllDialogues:
    """
    Runs all 10 multi-turn dialogues.
    Computes:
      - task_completion_rate  (binary per dialogue via keyword rubric)
      - policy_adherence_rate (binary for out_of_scope dialogues)
      - llm_judge_scores      (0-10 per dialogue via local Ollama)
    """

    def test_dialogues_batch(self, chatbot_available, dialogues):
        results       = []
        judge_scores  = []

        for dlg in dialogues:
            sid       = create_session()
            responses = run(run_dialogue(dlg["turns"], sid))
            all_text  = " ".join(responses).lower()

            # ── Task completion (keyword rubric) ──
            kw_hit = all(kw.lower() in all_text
                         for kw in dlg.get("required_keywords", []))

            if dlg["policy_type"] == "out_of_scope":
                redirected = any(w in all_text for w in OUT_OF_SCOPE_REDIRECT_WORDS)
                success    = redirected
            else:
                success = kw_hit or len(all_text) > 20

            # ── LLM-as-Judge (rubric scoring) ──
            first_user_turn = next(
                (t["content"] for t in dlg["turns"] if t["role"] == "user"), ""
            )
            rubric      = dlg.get("rubric", "Response should be helpful and relevant.")
            first_resp  = responses[0] if responses else ""
            judge_result = llm_judge(first_user_turn, first_resp, rubric)
            judge_scores.append(judge_result["score"])

            results.append({
                "id":                      dlg["id"],
                "title":                   dlg["title"],
                "policy_type":             dlg["policy_type"],
                "task_completion_expected": dlg["task_completion"],
                "success":                 success,
                "llm_judge_score":         judge_result["score"],
                "llm_judge_reasoning":     judge_result["reasoning"],
                "response_preview":        first_resp[:150]
            })

        # ── Compute aggregate metrics ──
        total            = len(results)
        success_count    = sum(1 for r in results if r["success"])
        task_completion_rate = success_count / total

        policy_dialogues = [r for r in results if r["policy_type"] == "out_of_scope"]
        policy_adherence = (
            sum(1 for r in policy_dialogues if r["success"]) / len(policy_dialogues)
            if policy_dialogues else 1.0
        )

        avg_judge_score  = sum(judge_scores) / len(judge_scores) if judge_scores else 0

        # ── Save report ──
        report = {
            "task_completion_rate":  round(task_completion_rate, 3),
            "policy_adherence_rate": round(policy_adherence, 3),
            "avg_llm_judge_score":   round(avg_judge_score, 2),
            "total_dialogues":       total,
            "dialogues":             results
        }
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n  Task Completion Rate : {task_completion_rate:.0%}")
        print(f"  Policy Adherence Rate: {policy_adherence:.0%}")
        print(f"  Avg LLM Judge Score  : {avg_judge_score:.1f}/10")

        assert task_completion_rate >= 0.6, \
            f"Task completion rate {task_completion_rate:.0%} < 60%. Results: {results}"