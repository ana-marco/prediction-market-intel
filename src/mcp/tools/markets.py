"""
MCP tools for querying prediction market data.

Live API data via PolymarketClient, with PostgreSQL fallback.
"""

import json
import logging

from fastmcp import FastMCP
from src.database.postgres import PostgresClient
from src.ingestion.polymarket import PolymarketClient

logger = logging.getLogger(__name__)


def _parse_yes_probability(market: dict) -> str:
    """Extract Yes probability from outcome prices.

    Handles both DB rows (outcome_prices, snake_case) and raw API
    responses (outcomePrices, camelCase). Values may be a list or
    a JSON-encoded string like '["0.0575", "0.9425"]'.
    """
    prices = market.get("outcome_prices") or market.get("outcomePrices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except (json.JSONDecodeError, TypeError):
            return "N/A"
    if prices and isinstance(prices, list) and len(prices) > 0:
        try:
            return f"{float(prices[0]) * 100:.1f}%"
        except (ValueError, TypeError):
            pass
    return "N/A"


def _format_market(m: dict) -> dict:
    """Format a market dict (from API or DB) into the tool response schema.

    Accepts both live API dicts (camelCase keys like volume24hr, slug)
    and PostgreSQL row dicts (snake_case keys like volume_24h, source_url).
    """
    vol = m.get("volume24hr") or m.get("volume_24h")
    try:
        vol_str = f"${float(vol):,.0f}" if vol else "N/A"
    except (ValueError, TypeError):
        vol_str = "N/A"
    return {
        "question": m.get("question"),
        "yes_probability": _parse_yes_probability(m),
        "volume_24h": vol_str,
        "category": m.get("category") or "Unknown",
        "url": (
            m.get("source_url")
            or f"https://polymarket.com/event/{m.get('slug', '')}"
        ),
    }


def register_market_tools(mcp: FastMCP):
    """Register market-related tools with the MCP server."""

    @mcp.tool()
    def search_markets(query: str, limit: int = 5) -> dict:
        """Search prediction markets by keyword using live Polymarket data.

        Args:
            query: Search term (e.g., "Iran", "Fed", "Bitcoin")
            limit: Maximum number of results (default 5)

        Returns:
            Dict with markets list and source metadata
        """
        # Live API: fetch active markets and filter client-side.
        # Polymarket's search endpoint is unreliable, so we use
        # get_markets with keyword filtering instead.
        try:
            client = PolymarketClient(use_cache=False)
            all_markets = client.get_markets(
                limit=100, active=True,
                order="volume24hr", ascending=False,
            )
            q_lower = query.lower()
            matches = [
                m for m in all_markets
                if q_lower in (m.get("question", "") or "").lower()
            ][:limit]
            if matches:
                formatted = [_format_market(m) for m in matches]
                return {
                    "markets": formatted,
                    "count": len(formatted),
                    "source": "polymarket",
                    "source_type": "prediction_market",
                }
        except Exception as e:
            logger.warning(f"Live Polymarket search failed: {e}")

        # Fall back to PostgreSQL full-text search
        try:
            db = PostgresClient()
            markets = db.search_markets(query, limit=limit)
            formatted = [_format_market(m) for m in markets]
            return {
                "markets": formatted,
                "count": len(formatted),
                "source": "polymarket",
                "source_type": "prediction_market",
            }
        except Exception as e:
            return {"error": str(e), "markets": []}

    @mcp.tool()
    def get_top_markets(
        category: str = None, limit: int = 10
    ) -> dict:
        """Get top prediction markets by trading volume from live Polymarket data.

        Args:
            category: Optional category filter
            limit: Maximum number of results (default 10)

        Returns:
            Dict with markets list and source metadata
        """
        # Try live API first
        try:
            client = PolymarketClient(use_cache=False)
            markets = client.get_markets(
                limit=limit, active=True,
                order="volume24hr", ascending=False,
            )
            if category:
                markets = [
                    m for m in markets
                    if category.lower() in (
                        m.get("category", "") or ""
                    ).lower()
                ]
            if markets:
                formatted = [_format_market(m) for m in markets]
                return {
                    "markets": formatted,
                    "count": len(formatted),
                    "source": "polymarket",
                    "source_type": "prediction_market",
                }
        except Exception as e:
            logger.warning(f"Live Polymarket fetch failed: {e}")

        # Fall back to PostgreSQL
        try:
            db = PostgresClient()
            markets = db.get_markets(
                category=category, limit=limit
            )
            formatted = [_format_market(m) for m in markets]
            return {
                "markets": formatted,
                "count": len(formatted),
                "source": "polymarket",
                "source_type": "prediction_market",
            }
        except Exception as e:
            return {"error": str(e), "markets": []}
