"""
Unit tests for pure functions that don't require database connections.

Tests cover:
- Market probability parsing (various formats)
- Market data formatting (API vs DB schemas)
- Source extraction from agent tool messages
"""

import json

import pytest


# -- _parse_yes_probability tests --

from src.mcp.tools.markets import _parse_yes_probability


class TestParseYesProbability:
    """Handles both DB rows and raw API responses with different key names."""

    def test_list_input(self):
        market = {"outcome_prices": ["0.65", "0.35"]}
        assert _parse_yes_probability(market) == "65.0%"

    def test_json_string_input(self):
        market = {"outcome_prices": '["0.75", "0.25"]'}
        assert _parse_yes_probability(market) == "75.0%"

    def test_camelcase_key(self):
        market = {"outcomePrices": '["0.42", "0.58"]'}
        assert _parse_yes_probability(market) == "42.0%"

    def test_empty_dict(self):
        assert _parse_yes_probability({}) == "N/A"

    def test_none_prices(self):
        market = {"outcome_prices": None}
        assert _parse_yes_probability(market) == "N/A"

    def test_empty_list(self):
        market = {"outcome_prices": []}
        assert _parse_yes_probability(market) == "N/A"

    def test_invalid_json_string(self):
        market = {"outcome_prices": "not json"}
        assert _parse_yes_probability(market) == "N/A"

    def test_zero_probability(self):
        market = {"outcome_prices": ["0", "1"]}
        assert _parse_yes_probability(market) == "0.0%"

    def test_full_probability(self):
        market = {"outcome_prices": ["1.0", "0.0"]}
        assert _parse_yes_probability(market) == "100.0%"


# -- _format_market tests --

from src.mcp.tools.markets import _format_market


class TestFormatMarket:
    """Handles both live API dicts and PostgreSQL row dicts."""

    def test_api_format(self):
        market = {
            "question": "Will X happen?",
            "outcomePrices": '["0.65", "0.35"]',
            "volume24hr": 1234567.89,
            "slug": "will-x-happen",
            "category": "Politics",
        }
        result = _format_market(market)
        assert result["question"] == "Will X happen?"
        assert result["yes_probability"] == "65.0%"
        assert result["volume_24h"] == "$1,234,568"
        assert "polymarket.com" in result["url"]
        assert result["category"] == "Politics"

    def test_db_format(self):
        market = {
            "question": "Will Y happen?",
            "outcome_prices": '["0.30", "0.70"]',
            "volume_24h": 500000,
            "source_url": "https://polymarket.com/event/test",
            "category": None,
        }
        result = _format_market(market)
        assert result["question"] == "Will Y happen?"
        assert result["yes_probability"] == "30.0%"
        assert result["volume_24h"] == "$500,000"
        assert result["url"] == "https://polymarket.com/event/test"
        assert result["category"] == "Unknown"

    def test_missing_volume(self):
        market = {"question": "Test?"}
        result = _format_market(market)
        assert result["volume_24h"] == "N/A"

    def test_missing_everything(self):
        result = _format_market({})
        assert result["question"] is None
        assert result["yes_probability"] == "N/A"
        assert result["volume_24h"] == "N/A"
        assert result["category"] == "Unknown"


# -- _extract_sources_and_tools tests --

from src.agent.agent import _extract_sources_and_tools


def _make_tool_message(name, content):
    """Create a mock ToolMessage matching MCP's format."""
    from langchain_core.messages import ToolMessage

    # MCP returns content as list of typed blocks
    if isinstance(content, dict):
        content = [{"type": "text", "text": json.dumps(content)}]
    return ToolMessage(
        content=content, name=name, tool_call_id="test"
    )


class TestExtractSourcesAndTools:
    """Parses MCP ToolMessage content blocks for source attribution."""

    def test_extracts_top_level_source(self):
        msg = _make_tool_message("search_markets", {
            "source": "polymarket",
            "source_type": "prediction_market",
            "markets": [],
        })
        sources, tools = _extract_sources_and_tools([msg])
        assert tools == ["search_markets"]
        assert {"source": "polymarket", "source_type": "prediction_market"} in sources

    def test_extracts_nested_urls(self):
        msg = _make_tool_message("search_markets", {
            "source": "polymarket",
            "source_type": "prediction_market",
            "markets": [
                {"question": "Test?", "url": "https://example.com/1"},
                {"question": "Test2?", "url": "https://example.com/2"},
            ],
        })
        sources, tools = _extract_sources_and_tools([msg])
        urls = [s["url"] for s in sources if "url" in s]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls

    def test_deduplicates_sources(self):
        msg1 = _make_tool_message("search_markets", {
            "source": "polymarket",
            "source_type": "prediction_market",
            "markets": [],
        })
        msg2 = _make_tool_message("search_markets", {
            "source": "polymarket",
            "source_type": "prediction_market",
            "markets": [],
        })
        sources, tools = _extract_sources_and_tools([msg1, msg2])
        polymarket_sources = [
            s for s in sources
            if s.get("source") == "polymarket"
        ]
        assert len(polymarket_sources) == 1

    def test_handles_non_tool_messages(self):
        from langchain_core.messages import HumanMessage, AIMessage

        messages = [
            HumanMessage(content="test"),
            AIMessage(content="response"),
        ]
        sources, tools = _extract_sources_and_tools(messages)
        assert sources == []
        assert tools == []

    def test_handles_malformed_content(self):
        from langchain_core.messages import ToolMessage

        msg = ToolMessage(
            content="not json at all",
            name="bad_tool",
            tool_call_id="test",
        )
        sources, tools = _extract_sources_and_tools([msg])
        assert tools == ["bad_tool"]
        assert sources == []

    def test_empty_messages(self):
        sources, tools = _extract_sources_and_tools([])
        assert sources == []
        assert tools == []
