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

import chainlit as cl

from src.agent.agent import AgentResponse, run_agent_query
from src.database.postgres import PostgresClient

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

    # Show thinking step while agent works
    async with cl.Step(name="Agent Processing", type="tool") as step:
        step.input = message.content
        response = await cl.make_async(run_agent_query)(message.content)
        step.output = (
            f"Tools: {', '.join(response.tools_used) or 'none'} | "
            f"Latency: {response.latency_ms / 1000:.1f}s | "
            f"Success: {response.success}"
        )

    if not response.success:
        await cl.Message(
            content=f"**Error:** {response.error}"
        ).send()
        return

    # Show tool calls as individual steps for visibility
    if response.tools_used:
        for tool_name in response.tools_used:
            async with cl.Step(
                name=tool_name, type="tool"
            ) as tool_step:
                tool_step.output = "Called via MCP stdio"

    # Build sources element (displayed alongside response)
    sources_md = format_sources(response.sources)
    sources_element = cl.Text(
        name="Verified Sources",
        content=(
            "*These sources come from tool results, not the LLM. "
            "Compare against the response to check for hallucinations.*"
            f"\n\n{sources_md}"
        ),
        display="side",
    )

    # Send the main response with sources attached
    tools_str = (
        ", ".join(response.tools_used)
        if response.tools_used
        else "none"
    )
    latency = f"{response.latency_ms / 1000:.1f}s"

    await cl.Message(
        content=(
            f"{response.response}\n\n"
            f"---\n"
            f"*Tools: {tools_str} | Latency: {latency}*"
        ),
        elements=[sources_element],
    ).send()

    # Show agent logs in a follow-up collapsible step
    async with cl.Step(
        name="Agent Logs", type="tool"
    ) as logs_step:
        logs_step.output = format_agent_logs()
