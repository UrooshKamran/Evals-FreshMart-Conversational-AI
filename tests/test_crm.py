"""
tests/test_crm.py
Unit tests for the CRM tool — direct function calls, no LLM needed.
Run with: pytest tests/test_crm.py -v
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use a Windows-compatible temp path
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_crm_eval.db")

import crm_tool
crm_tool.DB_PATH = TEST_DB_PATH
crm_tool._init_db()

TEST_USER = "eval_test_user_001"


@pytest.fixture(autouse=True)
def clean_user():
    """Delete test user before each test for isolation."""
    import sqlite3
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.execute("DELETE FROM users WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM interactions WHERE user_id = ?", (TEST_USER,))
    conn.commit()
    conn.close()
    yield


class TestGetUserInfo:
    def test_new_user_returns_new_status(self):
        result = crm_tool.get_user_info(TEST_USER)
        assert result["status"] == "new_user"
        assert result["user_id"] == TEST_USER
        assert result["name"] is None

    def test_empty_user_id_returns_error(self):
        result = crm_tool.get_user_info("")
        assert "error" in result

    def test_none_user_id_returns_error(self):
        result = crm_tool.get_user_info(None)
        assert "error" in result


class TestUpdateUserInfo:
    def test_update_name(self):
        result = crm_tool.update_user_info(TEST_USER, "name", "Ahmed")
        assert result["status"] == "updated"
        info = crm_tool.get_user_info(TEST_USER)
        assert info["name"] == "Ahmed"

    def test_update_phone(self):
        result = crm_tool.update_user_info(TEST_USER, "phone", "0300-1234567")
        assert result["status"] == "updated"
        info = crm_tool.get_user_info(TEST_USER)
        assert info["phone"] == "0300-1234567"

    def test_update_email(self):
        result = crm_tool.update_user_info(TEST_USER, "email", "test@example.com")
        assert result["status"] == "updated"
        info = crm_tool.get_user_info(TEST_USER)
        assert info["email"] == "test@example.com"

    def test_update_address(self):
        result = crm_tool.update_user_info(TEST_USER, "address", "House 5, Street 10, Rawalpindi")
        assert result["status"] == "updated"
        info = crm_tool.get_user_info(TEST_USER)
        assert info["address"] == "House 5, Street 10, Rawalpindi"

    def test_update_preferences_json(self):
        result = crm_tool.update_user_info(TEST_USER, "preferences", '{"dietary": "vegan"}')
        assert result["status"] == "updated"
        info = crm_tool.get_user_info(TEST_USER)
        assert info["preferences"].get("dietary") == "vegan"

    def test_invalid_field_returns_error(self):
        result = crm_tool.update_user_info(TEST_USER, "invalid_field", "value")
        assert "error" in result

    def test_empty_user_id_returns_error(self):
        result = crm_tool.update_user_info("", "name", "Test")
        assert "error" in result

    def test_multiple_updates_persist(self):
        crm_tool.update_user_info(TEST_USER, "name", "Afroz")
        crm_tool.update_user_info(TEST_USER, "phone", "0311-9876543")
        info = crm_tool.get_user_info(TEST_USER)
        assert info["name"] == "Afroz"
        assert info["phone"] == "0311-9876543"
        assert info["status"] == "returning_user"


class TestStoreInteraction:
    def test_store_interaction_success(self):
        result = crm_tool.store_interaction(TEST_USER, "User asked about delivery hours")
        assert result["status"] == "stored"

    def test_store_empty_summary_returns_error(self):
        result = crm_tool.store_interaction(TEST_USER, "")
        assert "error" in result

    def test_store_empty_user_id_returns_error(self):
        result = crm_tool.store_interaction("", "Some summary")
        assert "error" in result

    def test_multiple_interactions_stored(self):
        crm_tool.store_interaction(TEST_USER, "First interaction")
        crm_tool.store_interaction(TEST_USER, "Second interaction")
        history = crm_tool.get_interaction_history(TEST_USER, limit=10)
        assert history["count"] == 2


class TestGetInteractionHistory:
    def test_empty_history_returns_zero(self):
        result = crm_tool.get_interaction_history(TEST_USER)
        assert result["status"] == "ok"
        assert result["count"] == 0

    def test_history_returns_correct_summaries(self):
        crm_tool.store_interaction(TEST_USER, "Ordered 2 apples")
        crm_tool.store_interaction(TEST_USER, "Asked about delivery")
        history = crm_tool.get_interaction_history(TEST_USER, limit=5)
        assert history["count"] == 2
        summaries = [i["summary"] for i in history["interactions"]]
        assert any("apple" in s.lower() for s in summaries)

    def test_limit_respected(self):
        for i in range(5):
            crm_tool.store_interaction(TEST_USER, f"Interaction {i}")
        history = crm_tool.get_interaction_history(TEST_USER, limit=3)
        assert len(history["interactions"]) == 3

    def test_empty_user_id_returns_error(self):
        result = crm_tool.get_interaction_history("")
        assert "error" in result


class TestCRMNegativeCases:
    def test_sql_injection_safe(self):
        result = crm_tool.update_user_info(TEST_USER, "name", "'; DROP TABLE users; --")
        assert "status" in result or "error" in result

    def test_very_long_value(self):
        long_val = "A" * 10000
        result = crm_tool.update_user_info(TEST_USER, "name", long_val)
        assert "status" in result or "error" in result