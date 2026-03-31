"""
MCP tools for querying FRED economic indicators.

Live API data via FREDClient, with PostgreSQL fallback.
"""

import logging

from fastmcp import FastMCP
from src.database.postgres import PostgresClient
from src.ingestion.fred import FREDClient

logger = logging.getLogger(__name__)


def register_economic_tools(mcp: FastMCP):
    """Register economic data tools with the MCP server."""

    @mcp.tool()
    def get_economic_indicator(
        series_id: str, limit: int = 5
    ) -> dict:
        """Get economic indicator values from live FRED API.

        Args:
            series_id: FRED series ID (e.g., "FEDFUNDS", "CPIAUCSL")
            limit: Number of historical values to return (default 5)

        Available indicators:
            FEDFUNDS, CPIAUCSL, UNRATE, DCOILWTICO,
            DGS10, VIXCLS, DTWEXBGS, T10Y2Y

        Returns:
            Dict with indicator values and source metadata
        """
        # Try live FRED API first
        try:
            client = FREDClient()
            data = client.get_series(series_id, limit=limit)
            if data and data.get("observations"):
                obs = data["observations"]
                formatted = []
                for o in obs:
                    if o.get("value") == ".":
                        continue
                    formatted.append({
                        "value": float(o["value"]),
                        "date": o["date"],
                        "units": data.get("units"),
                    })

                latest = formatted[0] if formatted else {}
                return {
                    "indicator": series_id.upper(),
                    "name": data.get("title", series_id),
                    "values": formatted[:limit],
                    "latest_value": latest.get("value"),
                    "latest_date": latest.get("date"),
                    "source": "fred",
                    "source_type": "economic_data",
                }
        except Exception as e:
            logger.warning(f"Live FRED API failed: {e}")

        # Fall back to PostgreSQL
        try:
            db = PostgresClient()
            values = db.get_indicator_history(
                series_id, limit=limit
            )
            if not values:
                return {
                    "error": f"Series '{series_id}' not found",
                    "values": [],
                }

            formatted = []
            for v in values:
                date = v.get("date")
                formatted.append({
                    "value": (
                        float(v["value"]) if v.get("value")
                        else None
                    ),
                    "date": (
                        date.strftime("%Y-%m-%d")
                        if date else "Unknown"
                    ),
                    "units": v.get("unit"),
                })

            latest = values[0] if values else {}
            latest_date = latest.get("date")
            return {
                "indicator": series_id.upper(),
                "name": latest.get("name", series_id),
                "values": formatted,
                "latest_value": (
                    float(latest["value"])
                    if latest.get("value") else None
                ),
                "latest_date": (
                    latest_date.strftime("%Y-%m-%d")
                    if latest_date else None
                ),
                "source": "fred",
                "source_type": "economic_data",
            }
        except Exception as e:
            return {"error": str(e), "values": []}

    @mcp.tool()
    def get_all_indicators() -> dict:
        """Get latest values for all economic indicators from live FRED.

        Returns:
            Dict with all indicator latest values
        """
        # Try live FRED API first
        try:
            client = FREDClient()
            results = client.get_all_indicators()
            if results:
                indicators = []
                for ind in results:
                    indicators.append({
                        "series_id": ind["series_id"],
                        "name": ind.get("name"),
                        "value": (
                            float(ind["value"])
                            if ind.get("value") else None
                        ),
                        "date": ind.get("date", "Unknown"),
                        "units": ind.get("units"),
                    })
                return {
                    "indicators": indicators,
                    "count": len(indicators),
                    "source": "fred",
                    "source_type": "economic_data",
                }
        except Exception as e:
            logger.warning(f"Live FRED API failed: {e}")

        # Fall back to PostgreSQL
        try:
            db = PostgresClient()
            series_ids = [
                "FEDFUNDS", "CPIAUCSL", "UNRATE", "DCOILWTICO",
                "DGS10", "VIXCLS", "DTWEXBGS", "T10Y2Y",
            ]
            indicators = []
            for series_id in series_ids:
                latest = db.get_latest_indicator(series_id)
                if latest:
                    date = latest.get("date")
                    indicators.append({
                        "series_id": series_id,
                        "name": latest.get("name"),
                        "value": (
                            float(latest["value"])
                            if latest.get("value") else None
                        ),
                        "date": (
                            date.strftime("%Y-%m-%d")
                            if date else "Unknown"
                        ),
                        "units": latest.get("unit"),
                    })
            return {
                "indicators": indicators,
                "count": len(indicators),
                "source": "fred",
                "source_type": "economic_data",
            }
        except Exception as e:
            return {"error": str(e), "indicators": []}
