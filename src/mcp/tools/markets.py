"""
MCP tools for querying prediction market data from PostgreSQL.
"""

from fastmcp import FastMCP
from src.database.postgres import PostgresClient


def _parse_yes_probability(market: dict) -> str:
    """Extract Yes probability from outcome_prices JSONB.

    outcome_prices may be a list or a JSON-encoded string like
    '["0.0575", "0.9425"]'. Index 0 is the Yes price.
    """
    import json

    prices = market.get("outcome_prices")
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


def register_market_tools(mcp: FastMCP):
    """Register market-related tools with the MCP server."""

    @mcp.tool()
    def search_markets(query: str, limit: int = 5) -> dict:
        """Search prediction markets by keyword.

        Args:
            query: Search term (e.g., "Iran", "Fed", "Bitcoin")
            limit: Maximum number of results (default 5)

        Returns:
            Dict with markets list and source metadata
        """
        try:
            db = PostgresClient()
            markets = db.search_markets(query, limit=limit)

            formatted = []
            for m in markets:
                formatted.append({
                    "question": m.get("question"),
                    "yes_probability": _parse_yes_probability(m),
                    "volume_24h": (
                        f"${float(m.get('volume_24h', 0)):,.0f}"
                        if m.get("volume_24h") else "N/A"
                    ),
                    "category": m.get("category") or "Unknown",
                    "url": m.get("source_url"),
                })

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
        """Get top prediction markets by trading volume.

        Args:
            category: Optional category filter
            limit: Maximum number of results (default 10)

        Returns:
            Dict with markets list and source metadata
        """
        try:
            db = PostgresClient()
            markets = db.get_markets(
                category=category, limit=limit
            )

            formatted = []
            for m in markets:
                formatted.append({
                    "question": m.get("question"),
                    "yes_probability": _parse_yes_probability(m),
                    "volume_24h": (
                        f"${float(m.get('volume_24h', 0)):,.0f}"
                        if m.get("volume_24h") else "N/A"
                    ),
                    "category": m.get("category") or "Unknown",
                    "url": m.get("source_url"),
                })

            return {
                "markets": formatted,
                "count": len(formatted),
                "source": "polymarket",
                "source_type": "prediction_market",
            }

        except Exception as e:
            return {"error": str(e), "markets": []}
