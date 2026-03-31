"""
LangChain agent that queries prediction markets, news, and economic data
via MCP tools over stdio transport.

Uses ChatOllama (local LLM) with tool-calling to decide which data sources
to query, then synthesises a response with source attribution.
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import nest_asyncio
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.sessions import StdioConnection
from langchain_mcp_adapters.tools import load_mcp_tools
from psycopg2.extras import Json as PgJson

from src.database.postgres import PostgresClient

nest_asyncio.apply()

logger = logging.getLogger(__name__)

PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
MCP_SERVER_PATH = str(Path(PROJECT_ROOT) / "src" / "mcp" / "server.py")
MODEL_NAME = "qwen2.5:7b"
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are a prediction market intelligence analyst with access to live data.

LIVE DATA TOOLS:
- search_markets(query): Search Polymarket for specific topics
- get_top_markets(): Highest-volume markets overview
- search_news(query): Search recent Guardian news articles
- get_recent_news(): Latest headlines
- get_economic_indicator(series_id): FRED data. IDs: FEDFUNDS, CPIAUCSL, UNRATE, DCOILWTICO, DGS10, VIXCLS, T10Y2Y
- get_all_indicators(): All economic indicators snapshot

HISTORICAL/SEMANTIC TOOLS:
- semantic_search(query): Find related content by meaning across all stored data
- find_related_content(topic): Cross-source context on a topic
- get_topic_graph(topic): Graph relationships linking markets, news, and indicators for a topic
- get_market_context(market_question): Deep context for a specific market via graph

RULES:
1. ALWAYS call tools before answering. Never invent data.
2. For broad questions, call 2-3 tools: markets + news, or markets + economic data.
3. For topic questions (e.g. "Iran"), call search_markets AND search_news.
4. For economic questions, call get_economic_indicator AND search_markets.
5. ALWAYS include semantic_search in your tool calls. It searches Reddit posts,
   articles, and markets by meaning -- it finds relevant content even when
   keywords don't match exactly.
6. If a live tool returns no results, try get_topic_graph as fallback.
7. Reference specific numbers from results: probabilities, prices, dates.
8. If no tool returns results, say so. Do not fabricate.
9. Keep responses to 2-4 paragraphs."""


@dataclass
class AgentResponse:
    """Structured response from the agent, separating content from metadata."""

    response: str
    sources: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    latency_ms: int = 0
    success: bool = True
    error: str | None = None


def _get_mcp_connection() -> StdioConnection:
    """Build the MCP stdio connection config for the subprocess server."""
    return StdioConnection(
        transport="stdio",
        command=sys.executable,
        args=[MCP_SERVER_PATH],
        env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
    )


def _extract_sources_and_tools(messages: list) -> tuple[list[dict], list[str]]:
    """Parse tool messages to extract source attribution and tool names.

    Returns (deduplicated sources list, tool names list).
    Sources come from the tools themselves, not the LLM -- this is the
    hallucination-checking mechanism: the LLM cannot fabricate citations.
    """
    sources = []
    tools_used = []
    seen_sources = set()

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue

        tools_used.append(msg.name)

        # MCP returns content as a list of typed blocks
        # e.g. [{"type": "text", "text": "{...json...}"}]
        raw = msg.content
        if isinstance(raw, list):
            text_parts = [
                b["text"] for b in raw
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            raw = text_parts[0] if text_parts else ""

        try:
            if isinstance(raw, str):
                content = json.loads(raw)
            else:
                content = raw
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(content, dict):
            continue

        # Top-level source fields (most tools have these)
        source_entry = {}
        if "source" in content:
            source_entry["source"] = content["source"]
        if "source_type" in content:
            source_entry["source_type"] = content["source_type"]

        if source_entry:
            key = (source_entry.get("source"), source_entry.get("source_type"))
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(source_entry)

        # Extract URLs from nested results (articles, markets)
        for item_list_key in ("markets", "articles", "results"):
            for item in content.get(item_list_key, []):
                url = item.get("url") or item.get("source_url")
                if url:
                    url_key = ("url", url)
                    if url_key not in seen_sources:
                        seen_sources.add(url_key)
                        sources.append({
                            "url": url,
                            "title": item.get("title") or item.get("question", ""),
                        })

    return sources, tools_used


def _log_to_postgres(query: str, response: AgentResponse) -> None:
    """Write agent interaction to the agent_logs table for observability."""
    try:
        db = PostgresClient()
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_logs (
                    query, tools_called, sources_cited,
                    response, latency_ms, success, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    query,
                    PgJson(response.tools_used),
                    PgJson(response.sources),
                    response.response,
                    response.latency_ms,
                    response.success,
                    response.error,
                ),
            )
    except Exception as e:
        logger.warning(f"Failed to log agent query: {e}")


async def _run_agent_async(query: str) -> AgentResponse:
    """Core async function: connect to MCP server, run LangChain agent loop."""
    connection = _get_mcp_connection()

    # session=None because we pass a connection config instead;
    # load_mcp_tools creates and manages the session internally
    tools = await load_mcp_tools(session=None, connection=connection)
    for t in tools:
        t.handle_tool_error = True
    logger.info(f"Loaded {len(tools)} MCP tools: {[t.name for t in tools]}")

    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0,
        num_predict=1024,
    )

    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    start = time.perf_counter()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"recursion_limit": MAX_ITERATIONS * 2},
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    messages = result["messages"]

    # Final AI message is the response
    response_text = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            response_text = msg.content
            break

    sources, tools_used = _extract_sources_and_tools(messages)

    return AgentResponse(
        response=response_text,
        sources=sources,
        tools_used=tools_used,
        latency_ms=elapsed_ms,
    )


def run_agent_query(query: str) -> AgentResponse:
    """Run a query through the prediction market intelligence agent.

    This is the main entry point. It spawns the MCP server as a subprocess,
    connects via stdio, runs the LangChain tool-calling loop, and returns
    a structured response with source attribution.
    """
    try:
        # Use a fresh event loop to avoid conflicts when called
        # from another async context (e.g., Chainlit's event loop)
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                _run_agent_async(query)
            )
        finally:
            loop.close()
        _log_to_postgres(query, response)
        return response
    except Exception as e:
        logger.error(f"Agent query failed: {e}", exc_info=True)
        error_response = AgentResponse(
            response=f"Sorry, I encountered an error: {e}",
            sources=[],
            tools_used=[],
            latency_ms=0,
            success=False,
            error=str(e),
        )
        _log_to_postgres(query, error_response)
        return error_response


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    query = sys.argv[1] if len(sys.argv) > 1 else "What are the top prediction markets right now?"
    result = run_agent_query(query)
    print(f"\n{'='*60}")
    print(f"Response:\n{result.response}")
    print(f"\nSources: {json.dumps(result.sources, indent=2)}")
    print(f"Tools used: {result.tools_used}")
    print(f"Latency: {result.latency_ms}ms")
    print(f"Success: {result.success}")
