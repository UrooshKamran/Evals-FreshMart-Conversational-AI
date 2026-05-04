
"""
conversation_manager.py - Assignment 4 Final
Fixes:
- CRM contact saves (name/phone/email/address) return hardcoded responses,
  bypassing the LLM entirely — the tiny model kept refusing despite OVERRIDE.
- Currency tool now parses amount + currencies directly from the message,
  not just from the cart total.
- Calculator invoked for pure math via regex.
- tool_ctx injected as final system message after cart state.
"""

import re
import concurrent.futures
import requests
import json
import logging
from system_prompt import SYSTEM_PROMPT
from cart_manager import CartManager
from memory_manager import MemoryManager
from intent_parser import parse_intent
from retrieval_module import retrieve, format_context, is_index_ready
import crm_tool
from tools.currency_tool import convert_currency, _normalize_currency
from tools.calculator_tool import calculate
import asyncio
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
MODEL = "qwen2.5:1.5b"
logger = logging.getLogger(__name__)

# ── Keyword lists ─────────────────────────────────────────────────────────────

CURRENCY_KW = ["rupee", "pkr", "convert", "in euros", "in pounds", "in pkr",
               "exchange", "currency", "usd to", "dollar to", "euros to",
               "pounds to", "how much is", "in usd", "in dollar"]
WEATHER_KW  = ["weather", "temperature", "rain", "sunny", "forecast", "degrees",
               "hot today", "cold today", "climate"]
GROCERY_CALC_KW = ["how much would", "what is the cost", "total cost", "price of", "cost me"]

# ── CRM regex ─────────────────────────────────────────────────────────────────
NAME_RE    = re.compile(r"my name is ([a-zA-Z]+)", re.IGNORECASE)
CALLME_RE  = re.compile(r"call me ([a-zA-Z]+)", re.IGNORECASE)
PHONE_RE   = re.compile(
    r"(?:my\s+)?(?:phone|mobile|cell|number|contact)(?:\s+(?:number|is|:))?\s*(?:is\s+)?([\d][\d\s\-\+]{6,})",
    re.IGNORECASE
)
EMAIL_RE   = re.compile(
    r"(?:my\s+)?(?:email|e-mail|mail)(?:\s+(?:is|address|:))?\s*(?:is\s+)?([\w.\-+]+@[\w.\-]+\.\w+)",
    re.IGNORECASE
)
ADDRESS_RE = re.compile(
    r"(?:i\s+live\s+in|my\s+(?:address|location|city)\s+is)\s+(.+?)(?:\.|$)",
    re.IGNORECASE
)
BACK_KW = ["i'm back", "im back", "i am back", "returning", "remember me",
           "do you remember", "what is my name", "whats my name"]

# ── Currency parsing regex ────────────────────────────────────────────────────
# Matches: "10 USD in PKR", "convert 50 euros to dollars", "100 PKR in USD"
CURRENCY_PARSE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(usd|pkr|eur|gbp|aed|dollar|dollars|euro|euros|rupee|rupees|pound|pounds)\b"
    r".*?\b(usd|pkr|eur|gbp|aed|dollar|dollars|euro|euros|rupee|rupees|pound|pounds)\b",
    re.IGNORECASE
)

# ── Pure math regex ───────────────────────────────────────────────────────────
PURE_MATH_RE = re.compile(
    r"(?:what\s+is|calculate|compute|how\s+much\s+is)\s+"
    r"([\d.]+)\s*"
    r"(times|multiplied\s+by|x|\*|divided\s+by|÷|/|plus|\+|minus|-|percent\s+of|%\s+of)\s*"
    r"([\d.]+)",
    re.IGNORECASE
)
OP_MAP = {
    "times": "*", "multiplied by": "*", "x": "*", "*": "*",
    "divided by": "/", "÷": "/", "/": "/",
    "plus": "+", "+": "+",
    "minus": "-", "-": "-",
    "percent of": "percent", "% of": "percent",
}


def _normalise_op(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return OP_MAP.get(key, key)


def _run(coro):
    """Run a coroutine safely regardless of event loop state."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=10)
        return loop.run_until_complete(coro)
    except Exception:
        try:
            return asyncio.run(coro)
        except Exception as ex:
            logger.error(f"Async run failed: {ex}")
            return {"error": str(ex)}


# ── Sentinel to bypass LLM ────────────────────────────────────────────────────
_BYPASS = "__BYPASS__"


class ConversationManager:

    END_SIGNALS = ["goodbye", "bye", "thank you, goodbye", "that's all",
                   "order confirmed", "see you", "thanks, bye"]

    def __init__(self, session_id: str):
        self.session_id   = session_id
        self.cart         = CartManager()
        self.memory       = MemoryManager(self.cart)
        self.is_active    = True
        self.turn_count   = 0
        self._crm_checked = False
        self._user_name   = None
        self._crm_user_id = session_id

    # ── CRM helpers ───────────────────────────────────────────────────────────

    def set_user_id(self, user_id: str):
        if user_id and user_id != self._crm_user_id:
            self._crm_user_id = user_id
            self._crm_checked = False

    def _crm_check_returning(self):
        if self._crm_checked:
            return
        self._crm_checked = True
        result = crm_tool.get_user_info(self._crm_user_id)
        if result.get("status") == "returning_user" and result.get("name"):
            self._user_name = result["name"]

    def _crm_save_name(self, name: str):
        crm_tool.update_user_info(self._crm_user_id, "name", name)
        self._user_name = name
        logger.info(f"[CRM] Saved name '{name}' for {self.session_id}")

    def _crm_save_phone(self, phone: str):
        crm_tool.update_user_info(self._crm_user_id, "phone", phone)
        logger.info(f"[CRM] Saved phone '{phone}' for {self.session_id}")

    def _crm_save_email(self, email: str):
        crm_tool.update_user_info(self._crm_user_id, "email", email)
        logger.info(f"[CRM] Saved email '{email}' for {self.session_id}")

    def _crm_save_address(self, address: str):
        crm_tool.update_user_info(self._crm_user_id, "address", address)
        logger.info(f"[CRM] Saved address '{address}' for {self.session_id}")

    def _crm_store_session(self):
        cart = self.cart.get_summary()
        crm_tool.store_interaction(
            self._crm_user_id,
            f"Session ended. Turns: {self.turn_count}. Cart: {cart}."
        )

    # ── Tool detection ────────────────────────────────────────────────────────

    def _detect_and_run_tools(self, user_message: str):
        """
        Detect tool needs and run the tool.

        Returns either:
          - A tuple (_BYPASS, "hardcoded reply string")  → skip LLM entirely
          - A plain string tool_ctx                      → inject as final system msg
          - ""                                           → no tool needed
        """
        msg = user_message.lower()

        # ── CRM: name ─────────────────────────────────────────────────────────
        m = NAME_RE.search(user_message)
        if m:
            name = m.group(1).capitalize()
            self._crm_save_name(name)
            return (_BYPASS, f"Nice to meet you, {name}! How can I help you shop at FreshMart today?")

        # "Call me Ali from now on"
        c = CALLME_RE.search(user_message)
        if c:
            name = c.group(1).capitalize()
            self._crm_save_name(name)
            return (_BYPASS, f"Got it! I'll call you {name} from now on. How can I help you today?")

        # ── CRM: phone ────────────────────────────────────────────────────────
        p = PHONE_RE.search(user_message)
        if p:
            phone = p.group(1).strip()
            self._crm_save_phone(phone)
            return (_BYPASS, f"Got it, I've noted your phone number {phone}. Is there anything else I can help you with?")

        # ── CRM: email ────────────────────────────────────────────────────────
        e = EMAIL_RE.search(user_message)
        if e:
            email = e.group(1).strip()
            self._crm_save_email(email)
            return (_BYPASS, f"Noted! I've saved your email {email}. How can I assist you with your shopping?")

        # ── CRM: address ──────────────────────────────────────────────────────
        a = ADDRESS_RE.search(user_message)
        if a:
            address = a.group(1).strip().rstrip(".")
            self._crm_save_address(address)
            return (_BYPASS, f"Got it, I've noted your location as {address}. How can I help you with your grocery shopping?")

        # ── CRM: returning user ───────────────────────────────────────────────
        if any(kw in msg for kw in BACK_KW):
            self._crm_check_returning()
            if self._user_name:
                return (_BYPASS, f"Welcome back, {self._user_name}! Great to see you again. How can I help you today?")
            return (_BYPASS, "Welcome back! Great to see you again. How can I help you today?")

        # ── Weather ───────────────────────────────────────────────────────────
        if any(kw in msg for kw in WEATHER_KW):
            city_m = re.search(r"in ([A-Za-z\s]+?)(?:\?|today|tomorrow|now|$)",
                                user_message, re.IGNORECASE)
            city = city_m.group(1).strip() if city_m else "Rawalpindi"
            try:
                from tools.weather_tool import get_weather
                result = _run(get_weather(city))
                if result and "error" not in result:
                    return (f"[TOOL RESULT: weather]\n"
                            f"City: {result.get('city')}, {result.get('country')}\n"
                            f"Condition: {result.get('description')}\n"
                            f"Temperature: {result.get('temperature')}°C "
                            f"(feels like {result.get('feels_like')}°C)\n"
                            f"Humidity: {result.get('humidity')}%\n"
                            f"Use these exact numbers in your response.")
            except Exception as ex:
                logger.warning(f"Weather tool failed: {ex}")
            return ("[TOOL NOTE] Weather API key not configured. "
                    "Tell the user you cannot fetch live weather and suggest "
                    "they check a weather app.")

        # ── Currency — parse amount + currencies directly from message ─────────
        if any(kw in msg for kw in CURRENCY_KW):
            cur_m = CURRENCY_PARSE_RE.search(user_message)
            if cur_m:
                amount    = float(cur_m.group(1))
                from_cur  = _normalize_currency(cur_m.group(2))
                to_cur    = _normalize_currency(cur_m.group(3))
                result = _run(convert_currency(amount, from_cur, to_cur))
                if result and "error" not in result:
                    return (f"[TOOL RESULT: currency]\n"
                            f"{amount} {from_cur} = {result.get('converted')} {to_cur}\n"
                            f"Rate: 1 {from_cur} = {result.get('exchange_rate')} {to_cur}\n"
                            f"Note: {result.get('note', '')}\n"
                            f"Report these exact numbers. No markdown.")
            # Fallback: try cart total
            cart_summary = self.cart.get_summary()
            amount = cart_summary.get("subtotal", 0) if isinstance(cart_summary, dict) else 0
            to_cur = "PKR"
            if "euro" in msg or " eur" in msg:    to_cur = "EUR"
            elif "pound" in msg or "gbp" in msg:  to_cur = "GBP"
            elif "dirham" in msg or "aed" in msg: to_cur = "AED"
            if amount > 0:
                result = _run(convert_currency(amount, "USD", to_cur))
                if result and "error" not in result:
                    return (f"[TOOL RESULT: currency]\n"
                            f"Cart total: ${result.get('amount')} USD\n"
                            f"Converted: {result.get('converted')} {to_cur}\n"
                            f"Rate: 1 USD = {result.get('exchange_rate')} {to_cur}\n"
                            f"Report these exact numbers. No markdown.")
            return "[TOOL NOTE] Could not determine amount to convert. Please specify e.g. '10 USD to PKR'."

        # ── Pure math — invoke calculator ─────────────────────────────────────
        math_m = PURE_MATH_RE.search(user_message)
        if math_m:
            a_val  = math_m.group(1)
            op_raw = math_m.group(2)
            b_val  = math_m.group(3)
            op     = _normalise_op(op_raw)
            expression = (f"({a_val} / 100) * {b_val}"
                          if op == "percent" else f"{a_val} {op} {b_val}")
            try:
                result = calculate(expression=expression)
                if result and "error" not in result:
                    answer = result.get("formatted", result.get("result", "?"))
                    return (f"OVERRIDE INSTRUCTION: "
                            f"The calculator result for {a_val} {op_raw} {b_val} is {answer}. "
                            f"Respond ONLY with this in plain text: "
                            f"'{a_val} {op_raw} {b_val} = {answer}'")
            except Exception as ex:
                logger.warning(f"Calculator failed for '{expression}': {ex}")

        # ── Grocery price hint ────────────────────────────────────────────────
        if any(kw in msg for kw in GROCERY_CALC_KW):
            return ("[TOOL HINT] User wants a price calculation. "
                    "Use exact catalog prices. Show arithmetic in plain text like: "
                    "3 x $2.50 = $7.50. Give the final total clearly. No markdown.")

        return ""

    # ── Prompt building ───────────────────────────────────────────────────────

    def _build_system(self, rag_ctx: str = "") -> str:
        parts = [SYSTEM_PROMPT]
        if self._user_name:
            parts.append(f"[CRM] User's name is {self._user_name}. Use their name naturally.")
        if rag_ctx:
            parts.append(rag_ctx)
        return "\n\n".join(parts)

    def _inject_tool_ctx(self, messages: list, tool_ctx: str) -> list:
        """Append tool_ctx as the final system message so LLM sees it last."""
        if not tool_ctx:
            return messages
        return messages + [{"role": "system", "content": tool_ctx}]

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _call_ollama(self, messages: list) -> str:
        def blocking_call():
            payload = {
                "model": MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 350, "temperature": 0.7}
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=120)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "").strip()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(blocking_call).result()

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        if not self.is_active:
            return "This session has ended. Please start a new conversation."
        parse_intent(user_message, self.cart)
        self._crm_check_returning()
        self.memory.add_message("user", user_message)

        tool_result = self._detect_and_run_tools(user_message)

        # CRM/returning-user: bypass LLM, return hardcoded response immediately
        if isinstance(tool_result, tuple) and tool_result[0] == _BYPASS:
            response = tool_result[1]
            self.memory.add_message("assistant", response)
            self.turn_count += 1
            return response

        # Normal LLM path
        rag_ctx  = self._get_rag(user_message)
        tool_ctx = tool_result if isinstance(tool_result, str) else ""
        msgs     = self.memory.build_messages(self._build_system(rag_ctx))
        msgs     = self._inject_tool_ctx(msgs, tool_ctx)
        response = self._call_ollama(msgs)
        self.memory.add_message("assistant", response)
        self.turn_count += 1
        if self._should_end(user_message):
            self._crm_store_session()
            self.is_active = False
        return response

    def stream_chat(self, user_message: str):
        if not self.is_active:
            yield "This session has ended. Please start a new conversation."
            return
        parse_intent(user_message, self.cart)
        self._crm_check_returning()
        self.memory.add_message("user", user_message)

        tool_result = self._detect_and_run_tools(user_message)

        # CRM bypass — stream the hardcoded response token by token
        if isinstance(tool_result, tuple) and tool_result[0] == _BYPASS:
            response = tool_result[1]
            yield response
            self.memory.add_message("assistant", response)
            self.turn_count += 1
            return

        # Normal LLM streaming path
        rag_ctx  = self._get_rag(user_message)
        tool_ctx = tool_result if isinstance(tool_result, str) else ""
        msgs     = self.memory.build_messages(self._build_system(rag_ctx))
        msgs     = self._inject_tool_ctx(msgs, tool_ctx)

        full_response = ""
        payload = {"model": MODEL, "messages": msgs, "stream": True,
                   "options": {"num_predict": 350, "temperature": 0.7}}
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                resp = pool.submit(
                    requests.post, OLLAMA_URL, json=payload, stream=True, timeout=120
                ).result()
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            yield token
                        if chunk.get("done"):
                            break
        except Exception as ex:
            msg = f"Sorry, I'm having trouble connecting. ({ex})"
            yield msg
            full_response = msg

        self.memory.add_message("assistant", full_response)
        self.turn_count += 1
        if self._should_end(user_message):
            self._crm_store_session()
            self.is_active = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_rag(self, msg: str) -> str:
        if not is_index_ready():
            return ""
        try:
            return format_context(retrieve(msg))
        except Exception:
            return ""

    def _should_end(self, msg: str) -> bool:
        return any(s in msg.lower() for s in self.END_SIGNALS)

    def reset_session(self):
        self.cart.clear()
        self.memory.reset()
        self.is_active    = True
        self.turn_count   = 0
        self._crm_checked = False

    def get_session_state(self) -> dict:
        return {
            "session_id":  self.session_id,
            "is_active":   self.is_active,
            "turn_count":  self.turn_count,
            "rag_ready":   is_index_ready(),
            "user_name":   self._user_name,
            "cart":        self.cart.get_summary()
        }
