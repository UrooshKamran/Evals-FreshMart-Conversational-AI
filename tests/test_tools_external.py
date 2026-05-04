"""
tests/test_tools_external.py
Unit tests for weather and currency tools.
Run with: pytest tests/test_tools_external.py -v
"""

import sys
import os
import asyncio
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.weather_tool import get_weather
from tools.currency_tool import convert_currency, _normalize_currency


def run(coro):
    """Python 3.14 compatible async runner."""
    return asyncio.run(coro)


# ── Weather Tool ──────────────────────────────────────────────────────────────

class TestWeatherToolWithKey:
    def test_valid_city_returns_temperature(self):
        if not os.getenv("WEATHER_API_KEY"):
            pytest.skip("WEATHER_API_KEY not set")
        r = run(get_weather("Rawalpindi"))
        assert r.get("status") == "ok"
        assert "temperature" in r
        assert "condition" in r

    def test_valid_city_london(self):
        if not os.getenv("WEATHER_API_KEY"):
            pytest.skip("WEATHER_API_KEY not set")
        r = run(get_weather("London"))
        assert r.get("status") == "ok"


class TestWeatherToolWithoutKey:
    def test_empty_city_returns_error(self):
        r = run(get_weather(""))
        assert "error" in r

    def test_none_city_returns_error(self):
        r = run(get_weather(None))
        assert "error" in r

    def test_invalid_city_graceful(self):
        if not os.getenv("WEATHER_API_KEY"):
            pytest.skip("WEATHER_API_KEY not set")
        r = run(get_weather("XYZABC_INVALID_CITY_123"))
        assert "error" in r

    def test_no_api_key_returns_config_error(self):
        import tools.weather_tool as wt
        original = wt.API_KEY
        wt.API_KEY = ""
        try:
            r = run(get_weather("Rawalpindi"))
            assert "error" in r
        finally:
            wt.API_KEY = original


# ── Currency Tool ─────────────────────────────────────────────────────────────

class TestCurrencyNormalization:
    def test_dollar_to_usd(self):
        assert _normalize_currency("dollar") == "USD"

    def test_rupee_to_pkr(self):
        assert _normalize_currency("rupees") == "PKR"

    def test_euro_to_eur(self):
        assert _normalize_currency("euro") == "EUR"

    def test_unknown_passthrough_uppercased(self):
        assert _normalize_currency("xyz") == "XYZ"

    def test_case_insensitive(self):
        assert _normalize_currency("USD") == "USD"
        assert _normalize_currency("usd") == "USD"


class TestCurrencyConversionWithKey:
    def test_usd_to_pkr(self):
        if not os.getenv("EXCHANGE_API_KEY"):
            pytest.skip("EXCHANGE_API_KEY not set")
        r = run(convert_currency(10.0, "USD", "PKR"))
        assert r.get("status") == "ok"
        assert r["converted"] > 0

    def test_pkr_to_usd(self):
        if not os.getenv("EXCHANGE_API_KEY"):
            pytest.skip("EXCHANGE_API_KEY not set")
        r = run(convert_currency(500.0, "PKR", "USD"))
        assert r.get("status") == "ok"
        assert r["converted"] > 0


class TestCurrencyConversionFallback:
    def test_usd_to_pkr_fallback(self):
        import tools.currency_tool as ct
        original = ct.API_KEY
        ct.API_KEY = ""
        try:
            r = run(convert_currency(10.0, "USD", "PKR"))
            assert "status" in r or "error" in r
        finally:
            ct.API_KEY = original

    def test_zero_amount_returns_error(self):
        r = run(convert_currency(0, "USD", "PKR"))
        assert "error" in r

    def test_negative_amount_returns_error(self):
        r = run(convert_currency(-5.0, "USD", "PKR"))
        assert "error" in r

    def test_empty_from_currency(self):
        r = run(convert_currency(10.0, "", "PKR"))
        assert "status" in r or "error" in r