"""
MCP tools for querying prediction market data from PostgreSQL.
"""

from fastmcp import FastMCP
from src.database.postgres import PostgresClient


def register_market_tools(mcp: FastMCP):
    """Register market-related tools with the MCP server."""
    
    @mcp.tool()
    def search_markets(query: str, limit: int = 5) -> dict:
        """
        Search prediction markets by keyword.
        
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
                    "yes_probability": f"{float(m.get('outcome_yes_price', 0))*100:.1f}%" if m.get('outcome_yes_price') else "N/A",
                    "volume_24h": f"${float(m.get('volume_24h', 0)):,.0f}" if m.get('volume_24h') else "N/A",
                    "category": m.get("category") or "Unknown",
                    "url": m.get("source_url")
                })
            
            return {
                "markets": formatted,
                "count": len(formatted),
                "source": "polymarket",
                "source_type": "prediction_market"
            }
            
        except Exception as e:
            return {"error": str(e), "markets": []}
    
    
    @mcp.tool()
    def get_top_markets(category: str = None, limit: int = 10) -> dict:
        """
        Get top prediction markets by trading volume.
        
        Args:
            category: Optional category filter (e.g., "Politics", "Crypto")
            limit: Maximum number of results (default 10)
            
        Returns:
            Dict with markets list and source metadata
        """
        try:
            db = PostgresClient()
            markets = db.get_markets(category=category, limit=limit)
            
            formatted = []
            for m in markets:
                formatted.append({
                    "question": m.get("question"),
                    "probability": f"{float(m.get('outcome_yes_price', 0))*100:.1f}%" if m.get('outcome_yes_price') else "N/A",
                    "volume_24h": f"${float(m.get('volume_24h', 0)):,.0f}" if m.get('volume_24h') else "N/A",
                    "category": m.get("category") or "Unknown"
                })
            
            return {
                "markets": formatted,
                "count": len(formatted),
                "source": "polymarket",
                "source_type": "prediction_market"
            }
            
        except Exception as e:
            return {"error": str(e), "markets": []}
