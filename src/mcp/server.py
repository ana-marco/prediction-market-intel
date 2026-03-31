"""
MCP Server for Prediction Market Intelligence.

Exposes tools for querying prediction markets, news, economic data,
and performing semantic search across all content.
"""

from fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("prediction-market-intel")


from src.mcp.tools.markets import register_market_tools
from src.mcp.tools.news import register_news_tools
from src.mcp.tools.economic import register_economic_tools
from src.mcp.tools.rag import register_rag_tools
from src.mcp.tools.graph import register_graph_tools

# Register all tools with the server
register_market_tools(mcp)
register_news_tools(mcp)
register_economic_tools(mcp)
register_rag_tools(mcp)
register_graph_tools(mcp)


if __name__ == "__main__":
    # Run the server
    mcp.run()
