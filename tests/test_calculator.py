"""
tests/test_calculator.py
Unit tests for the calculator tool.
Run with: pytest tests/test_calculator.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.calculator_tool import calculate


class TestCalculatorValid:
    def test_simple_addition(self):
        r = calculate("2 + 3")
        assert r["status"] == "ok"
        assert r["result"] == 5.0

    def test_multiplication(self):
        r = calculate("3 * 2.50")
        assert r["status"] == "ok"
        assert abs(r["result"] - 7.5) < 0.001

    def test_complex_expression(self):
        r = calculate("3 * 2.50 + 1.80")
        assert r["status"] == "ok"
        assert abs(r["result"] - 9.3) < 0.001

    def test_discount_calculation(self):
        # 15% discount on $45 = $38.25
        r = calculate("45 * 0.85")
        assert r["status"] == "ok"
        assert abs(r["result"] - 38.25) < 0.001

    def test_percentage(self):
        r = calculate("100 / 4")
        assert r["status"] == "ok"
        assert r["result"] == 25.0

    def test_parentheses(self):
        r = calculate("(2.50 + 1.80 + 3.50) * 2")
        assert r["status"] == "ok"
        assert abs(r["result"] - 15.6) < 0.001

    def test_exponentiation(self):
        r = calculate("2 ^ 3")
        assert r["status"] == "ok"
        assert r["result"] == 8.0

    def test_grocery_total(self):
        # 5 apples at $0.80 + 2 mangoes at $1.50
        r = calculate("5 * 0.80 + 2 * 1.50")
        assert r["status"] == "ok"
        assert abs(r["result"] - 7.0) < 0.001

    def test_result_formatted_integer(self):
        r = calculate("4 * 5")
        assert r["formatted"] == "20"

    def test_result_formatted_decimal(self):
        r = calculate("1 / 3")
        assert "." in r["formatted"]


class TestCalculatorInvalid:
    def test_division_by_zero(self):
        r = calculate("10 / 0")
        assert "error" in r
        assert "zero" in r["error"].lower()

    def test_empty_expression(self):
        r = calculate("")
        assert "error" in r

    def test_none_expression(self):
        r = calculate(None)
        assert "error" in r

    def test_malicious_code_blocked(self):
        r = calculate("__import__('os').system('ls')")
        assert "error" in r

    def test_letters_blocked(self):
        r = calculate("abc + def")
        assert "error" in r

    def test_whitespace_only(self):
        r = calculate("   ")
        assert "error" in r


class TestCalculatorEdgeCases:
    def test_very_large_number(self):
        r = calculate("999999 * 999999")
        assert r["status"] == "ok"

    def test_negative_result(self):
        r = calculate("3 - 10")
        assert r["status"] == "ok"
        assert r["result"] == -7.0

    def test_float_precision(self):
        r = calculate("0.1 + 0.2")
        # Should not crash
        assert r["status"] == "ok"