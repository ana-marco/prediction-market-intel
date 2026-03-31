"""
MCP tools for querying news articles from PostgreSQL.
"""

from fastmcp import FastMCP
from src.database.postgres import PostgresClient


def register_news_tools(mcp: FastMCP):
    """Register news-related tools with the MCP server."""
    
    @mcp.tool()
    def search_news(query: str, source: str = None, limit: int = 5) -> dict:
        """
        Search news articles by keyword.
        
        Args:
            query: Search term (e.g., "Iran", "inflation", "Trump")
            source: Optional source filter ("guardian" or "govuk")
            limit: Maximum number of results (default 5)
            
        Returns:
            Dict with articles list and source metadata
        """
        try:
            db = PostgresClient()
            articles = db.search_articles(query, limit=limit)
            
            # Filter by source if specified
            if source:
                articles = [a for a in articles if a.get("source", "").lower() == source.lower()]
            
            formatted = []
            for a in articles:
                published = a.get("published_at")
                formatted.append({
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "published": published.strftime("%Y-%m-%d") if published else "Unknown",
                    "url": a.get("url"),
                    "snippet": (a.get("content") or "")[:300] + "..." if a.get("content") else ""
                })
            
            return {
                "articles": formatted,
                "count": len(formatted),
                "sources": list(set(a["source"] for a in formatted if a.get("source"))),
                "source_type": "news"
            }
            
        except Exception as e:
            return {"error": str(e), "articles": []}
    
    
    @mcp.tool()
    def get_recent_news(source: str = None, limit: int = 10) -> dict:
        """
        Get most recent news articles.
        
        Args:
            source: Optional source filter ("guardian" or "govuk")
            limit: Maximum number of results (default 10)
            
        Returns:
            Dict with articles list and source metadata
        """
        try:
            db = PostgresClient()
            articles = db.get_articles(source=source, limit=limit)
            
            formatted = []
            for a in articles:
                published = a.get("published_at")
                formatted.append({
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "published": published.strftime("%Y-%m-%d") if published else "Unknown",
                    "url": a.get("url")
                })
            
            return {
                "articles": formatted,
                "count": len(formatted),
                "source_type": "news"
            }
            
        except Exception as e:
            return {"error": str(e), "articles": []}
