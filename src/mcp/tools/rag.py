"""
MCP tools for semantic search using ChromaDB embeddings.

These search by meaning (vector similarity), not keywords.
Complements the live API tools and graph relationship tools.
"""

import logging

from fastmcp import FastMCP
from src.database.chroma import ChromaClient

logger = logging.getLogger(__name__)


def _get_source_type(collection: str) -> str:
    """Map ChromaDB collection name to a human-readable source type."""
    mapping = {
        "markets": "prediction_market",
        "articles": "news",
        "reddit": "social_media",
    }
    return mapping.get(collection, "unknown")


def register_rag_tools(mcp: FastMCP):
    """Register RAG/semantic search tools with the MCP server."""

    @mcp.tool()
    def semantic_search(
        query: str, collection: str = None, limit: int = 5
    ) -> dict:
        """Semantic search across all content using vector embeddings.

        Finds content by meaning, not just keywords.
        E.g., "Iran conflict" finds "Tehran tensions" without exact match.

        Args:
            query: Natural language search query
            collection: Optional filter ("markets", "articles", "reddit")
            limit: Maximum results (default 5)

        Returns:
            Dict with relevant content and source metadata
        """
        try:
            chroma = ChromaClient()
            results = chroma.search(
                query=query,
                collection_name=collection,
                n_results=limit,
            )

            formatted = []
            for r in results:
                doc = r.get("document", "")
                formatted.append({
                    "content": (
                        doc[:500] + "..." if len(doc) > 500 else doc
                    ),
                    "collection": r.get("collection"),
                    "relevance": round(
                        1 - (r.get("distance") or 0), 3
                    ),
                    "metadata": r.get("metadata", {}),
                    "source_type": _get_source_type(
                        r.get("collection")
                    ),
                })

            return {
                "results": formatted,
                "count": len(formatted),
                "query": query,
                "source_type": "semantic_search",
            }

        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return {"error": str(e), "results": []}

    @mcp.tool()
    def find_related_content(
        topic: str, limit: int = 3
    ) -> dict:
        """Find related content across all sources for a topic.

        Combines semantic search across markets, news, and Reddit
        to provide comprehensive context on a topic.

        Args:
            topic: Topic to search for (e.g., "Federal Reserve", "Iran")
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
                "topic": topic,
            }

            for key, search_fn in [
                ("markets", chroma.search_markets),
                ("news", chroma.search_articles),
                ("reddit", chroma.search_reddit),
            ]:
                for r in search_fn(topic, n_results=limit):
                    organized[key].append({
                        "content": r.get("document", "")[:300],
                        "metadata": r.get("metadata", {}),
                    })

            return {
                "related_content": organized,
                "total_count": sum(
                    len(v) for k, v in organized.items()
                    if k != "topic"
                ),
                "source_type": "semantic_search",
            }

        except Exception as e:
            logger.warning(f"Related content search failed: {e}")
            return {"error": str(e), "related_content": {}}
