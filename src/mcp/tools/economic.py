"""
MCP tools for querying FRED economic indicators from PostgreSQL.
"""

from fastmcp import FastMCP
from src.database.postgres import PostgresClient


def register_economic_tools(mcp: FastMCP):
    """Register economic data tools with the MCP server."""
    
    @mcp.tool()
    def get_economic_indicator(series_id: str, limit: int = 5) -> dict:
        """
        Get economic indicator values from FRED.
        
        Args:
            series_id: FRED series ID (e.g., "FEDFUNDS", "CPIAUCSL", "UNRATE")
            limit: Number of historical values to return (default 5)
            
        Available indicators:
            - FEDFUNDS: Federal Funds Rate
            - CPIAUCSL: Consumer Price Index
            - UNRATE: Unemployment Rate
            - DCOILWTICO: Crude Oil Price (WTI)
            - DGS10: 10-Year Treasury Rate
            - VIXCLS: VIX Volatility Index
            - DTWEXBGS: Trade Weighted US Dollar Index
            - T10Y2Y: Yield Curve (10Y minus 2Y)
            
        Returns:
            Dict with indicator values and source metadata
        """
        try:
            db = PostgresClient()
            
            # Get historical values
            values = db.get_indicator_history(series_id, limit=limit)
            
            if not values:
                return {"error": f"Series '{series_id}' not found", "values": []}
            
            formatted = []
            for v in values:
                date = v.get("date")
                formatted.append({
                    "value": float(v.get("value")) if v.get("value") else None,
                    "date": date.strftime("%Y-%m-%d") if date else "Unknown",
                    "units": v.get("unit")
                })
            
            latest = values[0] if values else {}
            latest_date = latest.get("date")
            
            return {
                "indicator": series_id.upper(),
                "name": latest.get("name", series_id),
                "values": formatted,
                "latest_value": float(latest.get("value")) if latest.get("value") else None,
                "latest_date": latest_date.strftime("%Y-%m-%d") if latest_date else None,
                "source": "fred",
                "source_type": "economic_data"
            }
            
        except Exception as e:
            return {"error": str(e), "values": []}
    
    
    @mcp.tool()
    def get_all_indicators() -> dict:
        """
        Get latest values for all economic indicators.
        
        Returns:
            Dict with all indicator latest values
        """
        try:
            db = PostgresClient()
            
            # List of all series we track
            series_ids = [
                "FEDFUNDS", "CPIAUCSL", "UNRATE", "DCOILWTICO",
                "DGS10", "VIXCLS", "DTWEXBGS", "T10Y2Y"
            ]
            
            indicators = []
            for series_id in series_ids:
                latest = db.get_latest_indicator(series_id)
                if latest:
                    date = latest.get("date")
                    indicators.append({
                        "series_id": series_id,
                        "name": latest.get("name"),
                        "value": float(latest.get("value")) if latest.get("value") else None,
                        "date": date.strftime("%Y-%m-%d") if date else "Unknown",
                        "units": latest.get("unit")
                    })
            
            return {
                "indicators": indicators,
                "count": len(indicators),
                "source": "fred",
                "source_type": "economic_data"
            }
            
        except Exception as e:
            return {"error": str(e), "indicators": []}
