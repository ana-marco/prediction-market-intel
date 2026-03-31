"""
MCP tools for semantic search using ChromaDB embeddings.
"""

from fastmcp import FastMCP
from src.database.chroma import ChromaClient


def register_rag_tools(mcp: FastMCP):
    """Register RAG/semantic search tools with the MCP server."""
    
    @mcp.tool()
    def semantic_search(query: str, collection: str = None, limit: int = 5) -> dict:
        """
        Semantic search across all content using vector embeddings.
        
        This finds content by meaning, not just keywords.
        E.g., "Iran conflict" will find "Tehran tensions" even without exact match.
        
        Args:
            query: Natural language search query
            collection: Optional collection filter ("markets", "articles", "reddit")
                       If None, searches all collections.
            limit: Maximum results (default 5)
            
        Returns:
            Dict with relevant content and source metadata
        """
        try:
            chroma = ChromaClient()
            
            # Search using the client's method
            results = chroma.search(
                query=query,
                collection_name=collection,
                n_results=limit
            )
            
            formatted = []
            for r in results:
                doc = r.get("document", "")
                formatted.append({
                    "content": doc[:500] + "..." if len(doc) > 500 else doc,
                    "collection": r.get("collection"),
                    "relevance": round(1 - (r.get("distance") or 0), 3),
                    "metadata": r.get("metadata", {}),
                    "source_type": _get_source_type(r.get("collection"))
                })
            
            return {
                "results": formatted,
                "count": len(formatted),
                "query": query,
                "source_type": "semantic_search"
            }
            
        except Exception as e:
            return {"error": str(e), "results": []}
    
    
    @mcp.tool()
    def find_related_content(topic: str, limit: int = 3) -> dict:
        """
        Find related content across all sources for a topic.
        
        Combines semantic search across markets, news, and Reddit
        to provide comprehensive context on a topic.
        
        Args:
            topic: Topic to search for (e.g., "Federal Reserve", "Iran", "Bitcoin")
            limit: Results per source type (default 3)
            
        Returns:
            Dict with organized results by source type
        """
        try:
            chroma = ChromaClient()
            
            organized = {
                "markets": [],
                "news": [],
                "reddit": [],
                "topic": topic
            }
            
            # Search markets
            market_results = chroma.search_markets(topic, n_results=limit)
            for r in market_results:
                organized["markets"].append({
                    "content": r.get("document", "")[:300],
                    "metadata": r.get("metadata", {})
                })
            
            # Search articles
            article_results = chroma.search_articles(topic, n_results=limit)
            for r in article_results:
                organized["news"].append({
                    "content": r.get("document", "")[:300],
                    "metadata": r.get("metadata", {})
                })
            
            # Search Reddit
            reddit_results = chroma.search_reddit(topic, n_results=limit)
            for r in reddit_results:
                organized["reddit"].append({
                    "content": r.get("document", "")[:300],
                    "metadata": r.get("metadata", {})
                })
            
            return {
                "related_content": organized,
                "total_count": sum(len(v) for k, v in organized.items() if k != "topic"),
                "source_type": "semantic_search"
            }
            
        except Exception as e:
            return {"error": str(e), "related_content": {}}


def _get_source_type(collection: str) -> str:
    """Map collection name to source type."""
    mapping = {
        "markets": "prediction_market",
        "articles": "news",
        "reddit": "social_media"
    }
    return mapping.get(collection, "unknown")
