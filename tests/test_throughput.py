"""
tests/test_throughput.py
Section 2.3.2 — Throughput (Concurrency)

Simulates increasing concurrent WebSocket sessions to determine:
  - Maximum sustainable concurrency (all latency metrics below threshold)
  - Breakpoint (concurrency level where latency degrades sharply or errors spike)
  - Turns per second at sustainable concurrency level

Each simulated user sends 3 messages (within 3-5 turn requirement).
Thresholds: median TTFT < 15s, E2E < 60s (CPU-only LLM realistic values)

Requires: chatbot running at BASE_URL
Run with: pytest tests/test_throughput.py -v --timeout=600
"""

import sys, os, json, time, asyncio, statistics, platform, psutil
import pytest, websockets

BASE_URL  = os.getenv("CHATBOT_WS_URL",  "ws://localhost:8000/ws/chat/")
HTTP_BASE = os.getenv("CHATBOT_HTTP_URL", "http://localhost:8000")

# ── Thresholds (CPU-only LLM — realistic values) ─────────────────────────────
MAX_MEDIAN_TTFT = 15.0   # seconds — time to first token
MAX_MEDIAN_E2E  = 60.0   # seconds — full response time

# ── Test parameters ───────────────────────────────────────────────────────────
CONCURRENCY_LEVELS = [1, 2, 3, 5, 10]   # Users to test
MESSAGES_PER_USER  = 3                   # 3-5 turns per user (assignment req)

FIXED_MESSAGES = [
    "What are FreshMart delivery hours?",
    "Calculate 5 times 3.50",
    "Do you have same-day delivery?",
]


# ── Hardware info ─────────────────────────────────────────────────────────────

def get_hardware_info() -> dict:
    try:
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        ram_gb = "unknown"
    return {
        "os":        platform.system() + " " + platform.release(),
        "cpu_cores": os.cpu_count(),
        "ram_gb":    ram_gb,
        "python":    platform.python_version(),
        "model":     "qwen2.5:1.5b (CPU quantised)"
    }


# ── Core simulation ───────────────────────────────────────────────────────────

async def simulate_user(user_id: int) -> dict:
    """Simulate a single user sending MESSAGES_PER_USER messages sequentially."""
    session_id   = f"throughput_user_{user_id}_{int(time.time())}"
    user_results = []

    for i, msg in enumerate(FIXED_MESSAGES[:MESSAGES_PER_USER]):
        t_send   = time.perf_counter()
        t_first  = None
        t_last   = None
        tokens   = 0
        error    = None

        url = BASE_URL + session_id
        try:
            async with websockets.connect(
                url, open_timeout=30, ping_timeout=120
            ) as ws:
                await ws.send(json.dumps({"message": msg}))
                async for raw in ws:
                    t_now = time.perf_counter()
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if data.get("type") == "token" and data.get("data"):
                        tokens += 1
                        if t_first is None:
                            t_first = t_now
                        t_last = t_now
                    elif data.get("type") in ("done", "end", "complete", "stream_end"):
                        t_last = t_now
                        break
                    elif data.get("type") == "error":
                        error = data.get("message", "error")
                        break
        except Exception as e:
            error = str(e)

        user_results.append({
            "user_id":     user_id,
            "turn":        i,
            "message":     msg,
            "ttft":        round(t_first - t_send, 3) if t_first else None,
            "e2e":         round(t_last  - t_send, 3) if t_last  else None,
            "token_count": tokens,
            "error":       error
        })

    return {"user_id": user_id, "turns": user_results}


def stats(vals: list) -> dict:
    if not vals:
        return {"mean": None, "median": None, "p90": None, "p99": None}
    s = sorted(vals)
    n = len(s)
    return {
        "mean":   round(statistics.mean(s), 3),
        "median": round(statistics.median(s), 3),
        "p90":    round(s[int(n * 0.90)], 3),
        "p99":    round(s[min(int(n * 0.99), n - 1)], 3),
    }


async def run_concurrent_users(n_users: int) -> dict:
    """Launch n_users coroutines simultaneously and aggregate results."""
    t_start      = time.perf_counter()
    all_results  = await asyncio.gather(*[simulate_user(i) for i in range(n_users)])
    t_end        = time.perf_counter()

    all_turns    = [turn for ur in all_results for turn in ur["turns"]]
    valid_ttfts  = [t["ttft"] for t in all_turns if t["ttft"] is not None]
    valid_e2es   = [t["e2e"]  for t in all_turns if t["e2e"]  is not None]
    errors       = [t for t in all_turns if t["error"] is not None]

    total_turns  = len(all_turns)
    batch_time   = t_end - t_start
    error_rate   = len(errors) / total_turns if total_turns > 0 else 1.0
    tps          = total_turns / batch_time  if batch_time  > 0 else 0

    return {
        "n_users":       n_users,
        "total_turns":   total_turns,
        "error_count":   len(errors),
        "error_rate":    round(error_rate, 3),
        "batch_time_s":  round(batch_time, 3),
        "turns_per_sec": round(tps, 3),
        "ttft_stats":    stats(valid_ttfts),
        "e2e_stats":     stats(valid_e2es),
    }


def run(coro):
    return asyncio.run(coro)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chatbot_available():
    import requests
    try:
        requests.get(HTTP_BASE, timeout=10)
    except Exception:
        pytest.skip(f"Chatbot not reachable at {HTTP_BASE}. Run: docker compose up")


# ── Individual concurrency tests ──────────────────────────────────────────────

class TestThroughput:

    def test_single_user_baseline(self, chatbot_available):
        result = run(run_concurrent_users(1))
        _save(result)
        assert result["error_rate"] <= 0.5, \
            f"Single user error rate {result['error_rate']:.0%} too high"

    def test_2_concurrent_users(self, chatbot_available):
        result = run(run_concurrent_users(2))
        _save(result)
        assert result["error_rate"] <= 0.5, \
            f"Error rate {result['error_rate']:.0%} too high at 2 users"

    def test_3_concurrent_users(self, chatbot_available):
        result = run(run_concurrent_users(3))
        _save(result)
        assert result["error_rate"] <= 0.7, \
            f"Error rate {result['error_rate']:.0%} too high at 3 users"
        
    def test_10_concurrent_users(self, chatbot_available):
        result = run(run_concurrent_users(10))
        _save(result)
        assert result["error_rate"] <= 0.9, \
            f"Error rate {result['error_rate']:.0%} too high at 10 users"
        
    def test_full_concurrency_sweep(self, chatbot_available):
        """
        Full sweep across all concurrency levels.
        Determines:
          - max_sustainable_concurrency
          - breakpoint (where latency/errors degrade sharply)
          - turns_per_second at sustainable level
        """
        hardware = get_hardware_info()
        results  = []

        for n in CONCURRENCY_LEVELS:
            print(f"\n  Testing {n} concurrent user(s)...")
            result = run(run_concurrent_users(n))
            results.append(result)
            print(f"    TPS={result['turns_per_sec']:.2f} | "
                  f"TTFT_med={result['ttft_stats']['median']} | "
                  f"E2E_med={result['e2e_stats']['median']} | "
                  f"Errors={result['error_rate']:.0%}")

        # ── Max sustainable concurrency ──
        sustainable = [
            r for r in results
            if r["ttft_stats"]["median"] is not None
            and r["ttft_stats"]["median"] <= MAX_MEDIAN_TTFT
            and r["error_rate"] <= 0.5
        ]
        max_sustainable = max(
            (r["n_users"] for r in sustainable), default=0
        )

        # ── Breakpoint detection ──
        # Breakpoint = first concurrency level where TTFT jumps > 50% vs previous
        # OR error_rate exceeds 0.5
        breakpoint_n = None
        for i in range(1, len(results)):
            prev = results[i - 1]
            curr = results[i]
            prev_ttft = prev["ttft_stats"]["median"] or 0
            curr_ttft = curr["ttft_stats"]["median"] or 0
            ttft_jump = (curr_ttft - prev_ttft) / prev_ttft if prev_ttft > 0 else 0
            if curr["error_rate"] > 0.5 or ttft_jump > 0.5:
                breakpoint_n = curr["n_users"]
                break

        # ── TPS at sustainable level ──
        tps_at_sustainable = next(
            (r["turns_per_sec"] for r in results
             if r["n_users"] == max_sustainable), 0
        )

        # ── Comparison table ──
        table  = "\n## Throughput Concurrency Table\n\n"
        table += "| Users | TPS | TTFT med | TTFT p90 | TTFT p99 | E2E med | E2E p90 | Errors | Sustainable |\n"
        table += "|---|---|---|---|---|---|---|---|---|\n"
        for r in results:
            t   = r["ttft_stats"]
            e   = r["e2e_stats"]
            sus = "✅" if r in sustainable else "❌"
            bp  = " ← breakpoint" if r["n_users"] == breakpoint_n else ""
            table += (
                f"| {r['n_users']} "
                f"| {r['turns_per_sec']:.2f} "
                f"| {t['median']}s | {t['p90']}s | {t['p99']}s "
                f"| {e['median']}s | {e['p90']}s "
                f"| {r['error_rate']:.0%} "
                f"| {sus}{bp} |\n"
            )

        # ── Save full report ──
        report = {
            "hardware":                   hardware,
            "thresholds": {
                "max_median_ttft_s":      MAX_MEDIAN_TTFT,
                "max_median_e2e_s":       MAX_MEDIAN_E2E,
            },
            "concurrency_levels_tested":  CONCURRENCY_LEVELS,
            "messages_per_user":          MESSAGES_PER_USER,
            "max_sustainable_concurrency": max_sustainable,
            "breakpoint_concurrency":     breakpoint_n,
            "tps_at_sustainable":         tps_at_sustainable,
            "results":                    results,
            "comparison_table":           table
        }

        report_path = os.path.join(
            os.path.dirname(__file__), "..", "reports", "throughput_report.json"
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(table)
        print(f"\n  Max Sustainable Concurrency : {max_sustainable} users")
        print(f"  Breakpoint                  : {breakpoint_n} users")
        print(f"  TPS at sustainable level    : {tps_at_sustainable:.2f}")

        assert max_sustainable >= 1, \
            "System could not sustain even 1 concurrent user within latency thresholds"


def _save(result: dict):
    path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "throughput_log.json"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = []
    if os.path.exists(path):
        with open(path) as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    existing.append(result)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== FreshMart Throughput Benchmark ===\n")
    print(f"{'Users':>6} | {'TPS':>7} | {'TTFT med':>9} | {'E2E med':>8} | {'Errors':>7}")
    print("-" * 55)
    for n in CONCURRENCY_LEVELS:
        r = run(run_concurrent_users(n))
        print(
            f"{n:>6} | {r['turns_per_sec']:>7.2f} | "
            f"{str(r['ttft_stats']['median']):>9} | "
            f"{str(r['e2e_stats']['median']):>8} | "
            f"{r['error_rate']:>6.0%}"
        )