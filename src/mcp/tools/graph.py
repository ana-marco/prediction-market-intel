"""
MCP tools for querying Neo4j graph relationships.

Exposes topic-based graph traversal: find markets, articles, and
indicators connected through explicit relationships, not vector
similarity. Complements the RAG tools in rag.py.
"""

import logging

from fastmcp import FastMCP
from src.database.neo4j_db import Neo4jClient

logger = logging.getLogger(__name__)


def register_graph_tools(mcp: FastMCP):
    """Register graph relationship tools with the MCP server."""

    @mcp.tool()
    def get_topic_graph(topic: str, limit: int = 5) -> dict:
        """Get all markets, articles, and indicators linked to a topic
        via graph relationships.

        Args:
            topic: Topic name (e.g., "iran", "oil", "inflation",
                   "federal reserve", "bitcoin", "trump")
            limit: Max results per category (default 5)

        Returns:
            Dict with connected markets, articles, indicators
        """
        try:
            with Neo4jClient() as neo4j:
                result = neo4j.search_by_topic(topic, limit=limit)

            if not result:
                return {
                    "error": f"Topic '{topic}' not found in graph",
                    "markets": [],
                    "articles": [],
                }

            return {
                "topic": result["topic"],
                "markets": [
                    {
                        "question": m.get("question"),
                        "id": m.get("id"),
                    }
                    for m in result.get("markets", [])
                ],
                "articles": [
                    {
                        "title": a.get("title"),
                        "source": a.get("source"),
                    }
                    for a in result.get("articles", [])
                ],
                "indicators": [
                    {
                        "series_id": i.get("series_id"),
                        "name": i.get("name"),
                    }
                    for i in result.get("indicators", [])
                ],
                "source": "neo4j",
                "source_type": "graph_relationships",
            }

        except Exception as e:
            logger.warning(f"Neo4j graph query failed: {e}")
            return {"error": str(e), "markets": [], "articles": []}

    @mcp.tool()
    def get_market_context(market_question: str) -> dict:
        """Get full context for a market: related topics, articles,
        indicators, and similar markets via graph relationships.

        Args:
            market_question: The market question text to search for
                (e.g., "US forces enter Iran")

        Returns:
            Dict with topics, related articles, indicators, and
            similar markets
        """
        try:
            with Neo4jClient() as neo4j:
                # LLM passes natural language, not a market ID,
                # so we match by question text substring
                query = """
                MATCH (m:Market)
                WHERE toLower(m.question) CONTAINS toLower($text)
                RETURN m.id as id
                LIMIT 1
                """
                neo4j.connect()
                with neo4j.driver.session() as session:
                    result = session.run(
                        query, {"text": market_question}
                    )
                    record = result.single()

                if not record:
                    return {
                        "error": f"No market found matching "
                        f"'{market_question}'",
                    }

                context = neo4j.get_market_context(record["id"])

            if not context:
                return {"error": "No context found for market"}

            return {
                "market": context.get("market"),
                "topics": context.get("topics", []),
                "articles": [
                    {
                        "title": a.get("title"),
                        "source": a.get("source"),
                        "url": a.get("url"),
                    }
                    for a in context.get("articles", [])
                ],
                "indicators": [
                    {
                        "series_id": i.get("series_id"),
                        "name": i.get("name"),
                        "value": i.get("value"),
                    }
                    for i in context.get("indicators", [])
                ],
                "related_markets": [
                    {"question": m.get("question")}
                    for m in context.get("related_markets", [])
                ],
                "source": "neo4j",
                "source_type": "graph_relationships",
            }

        except Exception as e:
            logger.warning(f"Neo4j market context failed: {e}")
            return {"error": str(e)}
