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


FACT_CHECK_PROMPT = """You are a fact-checking agent that detects fabricated data and contradictions.

<input>
You receive a response written by a retrieval agent and the raw data it had access to.
</input>

<task>
Check whether the response contains fabricated numbers, invented events, or claims
that contradict the retrieved data. Only flag actual problems.
</task>

<rules>
- ONLY use the provided data as evidence. Never use your own knowledge.
- Reasonable interpretations and summaries are fine. Do NOT flag them.
- Only flag: wrong numbers, fabricated data points, or direct contradictions.
</rules>

<examples>
DO NOT flag: Response says "tensions are high" when data shows 65% conflict probability.
This is a reasonable interpretation.

DO flag: Response says "oil is at $95" when data shows $89.33.
This is a fabricated number.
</examples>

<output_format>
If all claims check out:
VERIFIED — All claims are consistent with the retrieved data.
CONFIDENCE: HIGH

If there are problems:
ISSUES FOUND:
- "[problematic claim]" — CONTRADICTED — [what the data actually says]
CONFIDENCE: LOW
</output_format>"""


@dataclass
class AgentResponse:
    """Structured response from the agent, separating content from metadata."""

    response: str
    sources: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    fact_check: dict | None = None
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


async def _fact_check(llm, response_text: str, tool_data: str) -> dict | None:
    """Fact-checking agent: verify retrieval agent's claims against raw tool data.

    Uses create_agent() with no tools, making it a real LangGraph agent
    that reasons over the evidence and produces structured verification.
    """
    try:
        verifier = create_agent(llm, tools=[], system_prompt=FACT_CHECK_PROMPT)
        result = await verifier.ainvoke(
            {"messages": [HumanMessage(content=(
                f"RETRIEVAL AGENT RESPONSE:\n{response_text}\n\n"
                f"RAW TOOL DATA:\n{tool_data}"
            ))]},
        )

        content = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content
                break

        confidence = "MEDIUM"
        for level in ("HIGH", "LOW", "MEDIUM"):
            if f"CONFIDENCE: {level}" in content:
                confidence = level
                break

        return {"verification": content, "confidence": confidence}
    except Exception as e:
        logger.warning(f"Fact-check agent failed: {e}")
        return None


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
        base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    )

    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    start = time.perf_counter()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"recursion_limit": MAX_ITERATIONS * 2},
    )

    messages = result["messages"]

    # Final AI message is the response
    response_text = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            response_text = msg.content
            break

    sources, tools_used = _extract_sources_and_tools(messages)

    # Collect raw tool data for fact-checker
    tool_data_parts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            raw = msg.content
            if isinstance(raw, list):
                text_parts = [
                    b["text"] for b in raw
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                raw = text_parts[0] if text_parts else ""
            tool_data_parts.append(f"[{msg.name}]: {raw}")

    # Second agent: fact-check the response against raw tool data
    fact_check = None
    if tool_data_parts and response_text:
        fact_check = await _fact_check(
            llm, response_text, "\n\n".join(tool_data_parts)
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return AgentResponse(
        response=response_text,
        sources=sources,
        tools_used=tools_used,
        fact_check=fact_check,
        latency_ms=elapsed_ms,
    )


def run_agent_query(query: str) -> AgentResponse:
    """Run a query through the prediction market intelligence agent.

    This is the main entry point. It spawns the MCP server as a subprocess,
    connects via stdio, runs the LangChain tool-calling loop, and returns
    a structured response with source attribution.
    """
    try:
        response = asyncio.run(_run_agent_async(query))
        _log_to_postgres(query, response)
        return response
    except BaseException as e:
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if args else "What are the top prediction markets right now?"

    if "--json" in sys.argv:
        # Machine-readable output for subprocess callers (e.g., Chainlit)
        result = run_agent_query(query)
        print(json.dumps({
            "response": result.response,
            "sources": result.sources,
            "tools_used": result.tools_used,
            "fact_check": result.fact_check,
            "latency_ms": result.latency_ms,
            "success": result.success,
            "error": result.error,
        }))
    else:
        result = run_agent_query(query)
        print(f"\n{'='*60}")
        print(f"Response:\n{result.response}")
        print(f"\nSources: {json.dumps(result.sources, indent=2)}")
        print(f"Tools used: {result.tools_used}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Success: {result.success}")
