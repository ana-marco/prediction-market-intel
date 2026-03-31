"""
MCP tools for querying news articles.

Live API data via GuardianClient, with PostgreSQL fallback.
Gov.uk articles are always served from PostgreSQL (no live API).
"""

import logging

from fastmcp import FastMCP
from src.database.postgres import PostgresClient
from src.ingestion.guardian import GuardianClient

logger = logging.getLogger(__name__)


def _format_article(a: dict) -> dict:
    """Format an article dict (from API or DB) into the tool response schema."""
    published = a.get("published_at")
    if isinstance(published, str):
        published_str = published[:10]
    elif published:
        published_str = published.strftime("%Y-%m-%d")
    else:
        published_str = "Unknown"

    snippet = a.get("summary") or (a.get("content") or "")[:300]
    if snippet and not snippet.endswith("..."):
        snippet = snippet[:300] + "..."

    return {
        "title": a.get("title"),
        "source": a.get("source", "guardian"),
        "published": published_str,
        "url": a.get("url"),
        "snippet": snippet,
    }


def register_news_tools(mcp: FastMCP):
    """Register news-related tools with the MCP server."""

    @mcp.tool()
    def search_news(
        query: str, source: str = None, limit: int = 5
    ) -> dict:
        """Search recent news articles by keyword using live Guardian data.

        Args:
            query: Search term (e.g., "Iran", "inflation", "Trump")
            source: Optional filter ("guardian" or "govuk")
            limit: Maximum number of results (default 5)

        Returns:
            Dict with articles list and source metadata
        """
        # Guardian live API (skip if user specifically wants govuk)
        if source != "govuk":
            try:
                client = GuardianClient()
                articles = client.search_articles(
                    query, days_back=7, max_results=limit,
                )
                if articles:
                    formatted = [_format_article(a) for a in articles]
                    return {
                        "articles": formatted,
                        "count": len(formatted),
                        "sources": list(set(
                            a["source"] for a in formatted
                            if a.get("source")
                        )),
                        "source_type": "news",
                    }
            except Exception as e:
                logger.warning(f"Live Guardian search failed: {e}")

        # Fall back to PostgreSQL (covers govuk and Guardian fallback)
        try:
            db = PostgresClient()
            articles = db.search_articles(query, limit=limit)
            if source:
                articles = [
                    a for a in articles
                    if a.get("source", "").lower() == source.lower()
                ]
            formatted = [_format_article(a) for a in articles]
            return {
                "articles": formatted,
                "count": len(formatted),
                "sources": list(set(
                    a["source"] for a in formatted
                    if a.get("source")
                )),
                "source_type": "news",
            }
        except Exception as e:
            return {"error": str(e), "articles": []}

    @mcp.tool()
    def get_recent_news(
        source: str = None, limit: int = 10
    ) -> dict:
        """Get most recent news articles from live Guardian feed.

        Args:
            source: Optional filter ("guardian" or "govuk")
            limit: Maximum number of results (default 10)

        Returns:
            Dict with articles list and source metadata
        """
        # Guardian live API for recent headlines
        if source != "govuk":
            try:
                client = GuardianClient()
                articles = client.search_articles(
                    "", days_back=3, max_results=limit,
                )
                if articles:
                    formatted = [_format_article(a) for a in articles]
                    return {
                        "articles": formatted,
                        "count": len(formatted),
                        "source_type": "news",
                    }
            except Exception as e:
                logger.warning(f"Live Guardian fetch failed: {e}")

        # Fall back to PostgreSQL
        try:
            db = PostgresClient()
            articles = db.get_articles(source=source, limit=limit)
            formatted = [_format_article(a) for a in articles]
            return {
                "articles": formatted,
                "count": len(formatted),
                "source_type": "news",
            }
        except Exception as e:
            return {"error": str(e), "articles": []}
