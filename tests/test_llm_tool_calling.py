"""
tests/test_llm_tool_calling.py
Section 2.2.2 & 2.2.3 — LLM Tool Calling Accuracy

Measures whether the LLM:
  1. Correctly triggers CRM tool with right arguments
  2. Correctly triggers Calculator, Weather, Currency tools
  3. Avoids false positives (calling tools when not needed)

Requires: chatbot running at BASE_URL (docker compose up)
Run with: pytest tests/test_llm_tool_calling.py -v --timeout=600
"""

import sys, os, json, time, asyncio, pytest, requests
import websockets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE_URL   = os.getenv("CHATBOT_WS_URL",  "ws://localhost:8000/ws/chat/")
HTTP_BASE  = os.getenv("CHATBOT_HTTP_URL", "http://localhost:8000")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "tool_calling_report.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_session() -> str:
    try:
        r = requests.post(f"{HTTP_BASE}/session/new", timeout=10)
        return r.json().get("session_id", str(int(time.time())))
    except Exception:
        return str(int(time.time()))


async def send_and_get(message: str, session_id: str) -> str:
    """Send a message via WS and return the full response text."""
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
                elif data.get("type") in ("done", "end", "error", "stream_end"):
                    break
    except Exception as e:
        return f"[ERROR: {e}]"
    return full.strip()


def ask(message: str) -> str:
    sid = create_session()
    return asyncio.run(send_and_get(message, sid))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chatbot_available():
    try:
        r = requests.get(HTTP_BASE, timeout=10)
        if r.status_code not in (200, 404):
            pytest.skip("Chatbot not reachable")
    except Exception:
        pytest.skip("Chatbot not reachable. Run: docker compose up")


@pytest.fixture(scope="module", autouse=True)
def warmup(chatbot_available):
    """Warm up the LLM model before tests."""
    try:
        sid = create_session()
        async def _w():
            async with websockets.connect(
                BASE_URL + sid, open_timeout=30, ping_timeout=120
            ) as ws:
                await ws.send(json.dumps({"message": "hi"}))
                async for raw in ws:
                    if json.loads(raw).get("type") in ("done", "token", "error"):
                        break
        asyncio.run(_w())
        time.sleep(2)
    except Exception:
        pass


# ── 2.2.2 CRM Tool — LLM Calling Accuracy ────────────────────────────────────

class TestCRMLLMAccuracy:
    """
    Tests whether the LLM correctly calls the CRM tool when user
    provides personal information that should be stored.
    """

    # Test cases: (utterance, expected_keyword_in_response)
    CRM_TRIGGER_CASES = [
        ("My name is Fatima.",              ["fatima", "name", "noted", "saved", "remember"]),
        ("My phone number is 0300-1234567", ["phone", "noted", "saved", "0300", "number"]),
        ("My email is fatima@example.com",  ["email", "noted", "saved", "fatima"]),
        ("I live in Rawalpindi.",            ["rawalpindi", "address", "noted", "saved"]),
        ("Call me Ali from now on.",         ["ali", "name", "noted", "remember"]),
    ]

    # False positive cases: utterances that should NOT trigger CRM
    CRM_FALSE_POSITIVE_CASES = [
        "What are your delivery hours?",
        "Calculate 5 times 3",
        "What is the weather in Lahore?",
    ]

    def test_crm_triggered_for_name(self, chatbot_available):
        resp = ask("My name is Fatima.")
        assert any(w in resp.lower() for w in ["fatima", "name", "noted", "saved", "remember", "nice"]), \
            f"CRM not triggered for name. Got: {resp[:200]}"

    def test_crm_triggered_for_phone(self, chatbot_available):
        resp = ask("My phone number is 0300-1234567")
        assert any(w in resp.lower() for w in ["phone", "noted", "saved", "0300", "number", "got it"]), \
            f"CRM not triggered for phone. Got: {resp[:200]}"

    def test_crm_triggered_for_email(self, chatbot_available):
        resp = ask("My email is fatima@example.com")
        assert any(w in resp.lower() for w in ["email", "noted", "saved", "fatima", "got it"]), \
            f"CRM not triggered for email. Got: {resp[:200]}"

    def test_crm_batch_accuracy(self, chatbot_available):
        """
        Batch accuracy test over all CRM trigger cases.
        Reports: accuracy rate and false positive rate.
        """
        correct  = 0
        total    = len(self.CRM_TRIGGER_CASES)
        results  = []

        for utterance, expected_keywords in self.CRM_TRIGGER_CASES:
            resp = ask(utterance)
            hit  = any(w in resp.lower() for w in expected_keywords)
            if hit:
                correct += 1
            results.append({
                "utterance": utterance,
                "expected_keywords": expected_keywords,
                "response_preview": resp[:150],
                "correct": hit
            })

        # False positive check
        fp_count = 0
        fp_results = []
        for utterance in self.CRM_FALSE_POSITIVE_CASES:
            resp = ask(utterance)
            # A false positive = response that looks like a CRM save confirmation
            is_fp = any(w in resp.lower() for w in ["saved your", "noted your", "i've saved"])
            if is_fp:
                fp_count += 1
            fp_results.append({
                "utterance": utterance,
                "response_preview": resp[:150],
                "false_positive": is_fp
            })

        accuracy     = correct / total
        fp_rate      = fp_count / len(self.CRM_FALSE_POSITIVE_CASES)

        # Save report
        report = {
            "crm_tool_calling_accuracy": round(accuracy, 3),
            "crm_false_positive_rate":   round(fp_rate, 3),
            "crm_trigger_results":       results,
            "crm_false_positive_results": fp_results
        }
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        try:
            with open(REPORT_PATH) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing.update(report)
        with open(REPORT_PATH, "w") as f:
            json.dump(existing, f, indent=2)

        print(f"\n  CRM Tool Calling Accuracy : {accuracy:.0%}")
        print(f"  CRM False Positive Rate   : {fp_rate:.0%}")

        assert accuracy >= 0.6, \
            f"CRM tool calling accuracy {accuracy:.0%} < 60%. Results: {results}"
        assert fp_rate <= 0.3, \
            f"CRM false positive rate {fp_rate:.0%} > 30%. Results: {fp_results}"


# ── 2.2.3 Calculator — LLM Invocation Accuracy ───────────────────────────────

class TestCalculatorLLMAccuracy:
    """
    Tests whether the LLM correctly uses the calculator tool
    and incorporates the result into its response.
    """

    CALC_CASES = [
        ("What is 15 multiplied by 4?",   ["60"]),
        ("Calculate 100 divided by 4",    ["25"]),
        ("What is 7 plus 8?",             ["15"]),
        ("How much is 3 times 2.50?",     ["7.5", "7.50"]),
        ("What is 20 percent of 500?",    ["100"]),
    ]

    def test_calculator_simple_multiply(self, chatbot_available):
        resp = ask("What is 15 multiplied by 4?")
        assert "60" in resp, f"Calculator not triggered or wrong result. Got: {resp[:200]}"

    def test_calculator_division(self, chatbot_available):
        resp = ask("Calculate 100 divided by 4")
        assert "25" in resp, f"Division result missing. Got: {resp[:200]}"

    def test_calculator_batch_accuracy(self, chatbot_available):
        correct = 0
        results = []
        for utterance, expected in self.CALC_CASES:
            resp = ask(utterance)
            hit  = any(e in resp for e in expected)
            if hit:
                correct += 1
            results.append({
                "utterance": utterance,
                "expected": expected,
                "response_preview": resp[:150],
                "correct": hit
            })

        accuracy = correct / len(self.CALC_CASES)

        try:
            with open(REPORT_PATH) as f:
                report = json.load(f)
        except Exception:
            report = {}
        report["calculator_llm_accuracy"] = round(accuracy, 3)
        report["calculator_results"]      = results
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n  Calculator LLM Accuracy: {accuracy:.0%}")
        assert accuracy >= 0.6, \
            f"Calculator LLM accuracy {accuracy:.0%} < 60%. Results: {results}"


# ── 2.2.3 Weather — LLM Invocation Accuracy ──────────────────────────────────

class TestWeatherLLMAccuracy:
    """
    Tests whether the LLM correctly calls the weather tool
    and uses the result in its response.
    """

    WEATHER_CASES = [
        ("What is the weather in Rawalpindi?",   ["weather", "temperature", "°", "celsius", "humid", "rawalpindi"]),
        ("Is it raining in Karachi today?",       ["weather", "karachi", "rain", "temperature", "condition"]),
        ("How is the weather in Lahore?",         ["weather", "lahore", "temperature", "condition"]),
    ]

    def test_weather_rawalpindi(self, chatbot_available):
        if not os.getenv("WEATHER_API_KEY"):
            pytest.skip("WEATHER_API_KEY not set")
        resp = ask("What is the weather in Rawalpindi?")
        assert any(w in resp.lower() for w in
                   ["weather", "temperature", "celsius", "humid", "condition"]), \
            f"Weather tool not triggered. Got: {resp[:200]}"

    def test_weather_batch_accuracy(self, chatbot_available):
        if not os.getenv("WEATHER_API_KEY"):
            pytest.skip("WEATHER_API_KEY not set")
        correct = 0
        results = []
        for utterance, expected_kws in self.WEATHER_CASES:
            resp = ask(utterance)
            hit  = any(w in resp.lower() for w in expected_kws)
            if hit:
                correct += 1
            results.append({
                "utterance": utterance,
                "response_preview": resp[:150],
                "correct": hit
            })

        accuracy = correct / len(self.WEATHER_CASES)

        try:
            with open(REPORT_PATH) as f:
                report = json.load(f)
        except Exception:
            report = {}
        report["weather_llm_accuracy"] = round(accuracy, 3)
        report["weather_results"]      = results
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n  Weather LLM Accuracy: {accuracy:.0%}")
        assert accuracy >= 0.6, \
            f"Weather LLM accuracy {accuracy:.0%} < 60%. Results: {results}"


# ── 2.2.3 Currency — LLM Invocation Accuracy ─────────────────────────────────

class TestCurrencyLLMAccuracy:
    """
    Tests whether the LLM correctly calls the currency conversion tool.
    """

    CURRENCY_CASES = [
        ("How much is 10 USD in PKR?",   ["pkr", "rupee", "2", "3", "convert"]),
        ("Convert 50 euros to dollars",   ["dollar", "usd", "50", "convert"]),
        ("What is 100 PKR in USD?",       ["usd", "dollar", "0.", "cent", "convert"]),
    ]

    def test_currency_usd_to_pkr(self, chatbot_available):
        if not os.getenv("EXCHANGE_API_KEY"):
            pytest.skip("EXCHANGE_API_KEY not set")
        resp = ask("How much is 10 USD in PKR?")
        assert any(w in resp.lower() for w in ["pkr", "rupee", "2", "3"]), \
            f"Currency tool not triggered. Got: {resp[:200]}"

    def test_currency_batch_accuracy(self, chatbot_available):
        if not os.getenv("EXCHANGE_API_KEY"):
            pytest.skip("EXCHANGE_API_KEY not set")
        correct = 0
        results = []
        for utterance, expected_kws in self.CURRENCY_CASES:
            resp = ask(utterance)
            hit  = any(w in resp.lower() for w in expected_kws)
            if hit:
                correct += 1
            results.append({
                "utterance": utterance,
                "response_preview": resp[:150],
                "correct": hit
            })

        accuracy = correct / len(self.CURRENCY_CASES)

        try:
            with open(REPORT_PATH) as f:
                report = json.load(f)
        except Exception:
            report = {}
        report["currency_llm_accuracy"] = round(accuracy, 3)
        report["currency_results"]      = results
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n  Currency LLM Accuracy: {accuracy:.0%}")
        assert accuracy >= 0.6, \
            f"Currency LLM accuracy {accuracy:.0%} < 60%. Results: {results}"