"""
Integration tests that verify database connections and MCP tools.

These tests require Docker databases to be running:
    docker compose up -d

Tests are automatically skipped if a database is unavailable.
"""

import asyncio
import json
import os
import sys

import pytest


# -- PostgreSQL tests --


@pytest.mark.integration
class TestPostgreSQL:
    """Verify PostgreSQL operations against the Docker container."""

    def test_connection(self, db):
        with db.get_cursor() as cur:
            cur.execute("SELECT 1 AS val")
            assert cur.fetchone()["val"] == 1

    def test_markets_exist(self, db):
        markets = db.get_markets(limit=5)
        assert len(markets) > 0
        assert "question" in markets[0]

    def test_search_markets(self, db):
        results = db.search_markets("Iran")
        assert len(results) > 0
        assert any(
            "iran" in r["question"].lower() for r in results
        )

    def test_articles_exist(self, db):
        articles = db.get_articles(limit=5)
        assert len(articles) > 0
        assert "title" in articles[0]

    def test_indicators_exist(self, db):
        latest = db.get_latest_indicator("FEDFUNDS")
        assert latest is not None
        assert latest["series_id"] == "FEDFUNDS"
        assert latest["value"] is not None

    def test_agent_logs_table(self, db):
        """Agent logs table exists and is queryable."""
        with db.get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM agent_logs"
            )
            result = cur.fetchone()
            assert result["cnt"] >= 0


# -- ChromaDB tests --


@pytest.mark.integration
class TestChromaDB:
    """Verify ChromaDB vector search against the Docker container."""

    def test_connection(self, chroma):
        stats = chroma.get_stats()
        assert isinstance(stats, dict)

    def test_collections_exist(self, chroma):
        stats = chroma.get_stats()
        assert stats.get("markets", 0) > 0
        assert stats.get("articles", 0) > 0

    def test_semantic_search(self, chroma):
        results = chroma.search(
            "Iran conflict", collection_name="markets", n_results=3
        )
        assert len(results) > 0


# -- MongoDB tests --


@pytest.mark.integration
class TestMongoDB:
    """Verify MongoDB operations against the Docker container."""

    def test_connection(self, mongo):
        count = mongo.count_posts()
        assert count >= 0

    def test_posts_exist(self, mongo):
        posts = mongo.get_posts(limit=5)
        assert len(posts) > 0

    def test_subreddit_stats(self, mongo):
        stats = mongo.get_subreddit_stats()
        assert len(stats) > 0


# -- Neo4j tests --


@pytest.mark.integration
class TestNeo4j:
    """Verify Neo4j graph queries against the Docker container."""

    def test_connection(self, neo4j_client):
        stats = neo4j_client.get_stats()
        assert stats.get("markets", 0) > 0

    def test_topic_search(self, neo4j_client):
        result = neo4j_client.search_by_topic("iran", limit=3)
        assert result is not None
        assert result["topic"] == "iran"
        assert len(result["markets"]) > 0

    def test_market_context(self, neo4j_client):
        # Get a market ID first
        result = neo4j_client.search_by_topic("iran", limit=1)
        if result and result["markets"]:
            market_id = result["markets"][0]["id"]
            context = neo4j_client.get_market_context(market_id)
            assert context is not None
            assert "topics" in context


# -- MCP Server test --


@pytest.mark.integration
class TestMCPServer:
    """Verify the MCP server starts and exposes all tools."""

    def _run_mcp(self, coro):
        """Run an async MCP operation in a fresh event loop."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _get_mcp_params(self):
        from mcp import StdioServerParameters

        return StdioServerParameters(
            command=sys.executable,
            args=["src/mcp/server.py"],
            env={**os.environ, "PYTHONPATH": "."},
        )

    def test_server_lists_tools(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def _check():
            params = self._get_mcp_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [t.name for t in tools.tools]

        tool_names = self._run_mcp(_check())
        assert len(tool_names) == 10
        assert "search_markets" in tool_names
        assert "semantic_search" in tool_names
        assert "get_topic_graph" in tool_names

    def test_search_markets_tool(self):
        """Call search_markets through MCP and verify it returns data."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def _call():
            params = self._get_mcp_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "search_markets", {"query": "Iran", "limit": 2}
                    )
                    return json.loads(result.content[0].text)

        data = self._run_mcp(_call())
        assert data["source"] == "polymarket"
        assert data["count"] > 0
        assert "question" in data["markets"][0]

    def test_semantic_search_tool(self):
        """Call semantic_search through MCP and verify it returns data."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def _call():
            params = self._get_mcp_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "semantic_search",
                        {"query": "Iran conflict", "limit": 2},
                    )
                    return json.loads(result.content[0].text)

        data = self._run_mcp(_call())
        assert data["count"] > 0
        assert len(data["results"]) > 0

    def test_get_topic_graph_tool(self):
        """Call get_topic_graph through MCP and verify it returns data."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def _call():
            params = self._get_mcp_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "get_topic_graph",
                        {"topic": "iran", "limit": 3},
                    )
                    return json.loads(result.content[0].text)

        data = self._run_mcp(_call())
        assert data["topic"] == "iran"
        assert data["source"] == "neo4j"
        assert len(data["markets"]) > 0
