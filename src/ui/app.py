"""
Chainlit UI for the Prediction Market Intelligence Agent.

Provides a chat interface that displays agent responses alongside
verified sources (hallucination checking) and shows tool calls
as visible steps in the conversation.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so src.* imports resolve
# when running: chainlit run src/ui/app.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from concurrent.futures import ThreadPoolExecutor

import chainlit as cl

from src.agent.agent import AgentResponse, run_agent_query
from src.database.postgres import PostgresClient

_executor = ThreadPoolExecutor(max_workers=1)

DEMO_QUERIES = [
    "What are the biggest risks prediction markets are pricing right now?",
    "What's happening with Iran according to markets and news?",
    "How do economic indicators relate to current market predictions?",
    "What topics are trending across prediction markets and news?",
    "Compare what markets predict vs what news is reporting about climate change",
]


def format_sources(sources: list[dict]) -> str:
    """Format verified sources as markdown.

    Sources are extracted from tool results by code, not generated
    by the LLM. This separation is the hallucination checking mechanism.
    """
    if not sources:
        return "*No sources were returned by the tools.*"

    lines = []
    for src in sources:
        title = src.get("title", "")
        url = src.get("url", "")
        source_name = src.get("source", "")
        source_type = src.get("source_type", "")

        if url:
            lines.append(f"- [{title or url}]({url})")
        elif source_name:
            label = source_name
            if source_type:
                label += f" ({source_type})"
            lines.append(f"- {label}")

    return "\n".join(lines)


def format_agent_logs() -> str:
    """Format recent agent logs from PostgreSQL as markdown."""
    try:
        db = PostgresClient()
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, query, tools_called,
                       latency_ms, success, error_message
                FROM agent_logs
                ORDER BY timestamp DESC
                LIMIT 10
                """
            )
            logs = cursor.fetchall()

        if not logs:
            return "*No agent logs yet.*"

        lines = []
        for log in logs:
            status = "OK" if log["success"] else "FAILED"
            ts = (
                log["timestamp"].strftime("%H:%M:%S")
                if log["timestamp"]
                else "?"
            )
            latency = (
                f"{log['latency_ms']}ms"
                if log["latency_ms"]
                else "n/a"
            )
            tools = (
                ", ".join(log["tools_called"])
                if log["tools_called"]
                else "none"
            )
            lines.append(
                f"**[{ts}]** {status} | {latency} | "
                f"Tools: {tools}\n> {log['query']}"
            )

        return "\n\n".join(lines)

    except Exception as e:
        return f"*Could not load agent logs: {e}*"


@cl.on_chat_start
async def start():
    """Send a welcome message with demo query suggestions."""
    demo_list = "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(DEMO_QUERIES)
    )
    await cl.Message(
        content=(
            "**Prediction Market Intelligence Agent**\n\n"
            "I track prediction markets, news, and economic signals. "
            "Ask a question and I'll cite my sources.\n\n"
            "**Try one of these:**\n"
            f"{demo_list}"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle user query: run agent, display response + sources."""
    msg = cl.Message(content="")
    await msg.send()

    # Run agent in a thread to avoid async conflicts
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            _executor, run_agent_query, message.content
        )
    except Exception as e:
        msg.content = f"**Execution error:** `{type(e).__name__}: {e}`"
        await msg.update()
        return

    if not response.success:
        msg.content = f"**Error:** {response.error}"
        await msg.update()
        return

    # Build response with metadata
    tools_str = (
        ", ".join(response.tools_used)
        if response.tools_used
        else "none"
    )
    latency = f"{response.latency_ms / 1000:.1f}s"

    # Sources section (hallucination checking: from tools, not LLM)
    sources_md = format_sources(response.sources)

    # Fact-check section (AI-assisted verification by second agent)
    fact_check_md = ""
    if response.fact_check:
        confidence = response.fact_check.get("confidence", "N/A")
        verification = response.fact_check.get("verification", "")

        if confidence == "HIGH":
            fact_check_md = (
                "\n\n*Fact-check: all claims verified against source data.*"
            )
        else:
            fact_check_md = (
                f"\n\n### AI-Assisted Verification\n"
                f"**Confidence: {confidence}**\n\n"
                f"{verification}\n\n"
                f"*Verified by a separate fact-checking agent "
                f"against raw tool data.*"
            )

    msg.content = (
        f"{response.response}\n\n"
        f"---\n"
        f"**Tools used:** {tools_str} | **Latency:** {latency}\n\n"
        f"### Sources\n"
        f"{sources_md}"
        f"{fact_check_md}"
    )
    await msg.update()
