# Prediction Market Intelligence Agent

An AI agent that monitors prediction markets, news, and economic data to provide event risk intelligence.

## What can I ask?

- "What's happening with Iran?"
- "What are markets saying about the Fed?"
- "What's driving oil prices?"
- "Will there be a recession?"
- "What is the current VIX level?"

## How it works

1. Your question is sent to a **retrieval agent** that queries live data via 10 MCP tools
2. Sources include Polymarket, The Guardian, FRED economic data, Reddit, and gov.uk
3. A **fact-checking agent** verifies the response against the raw data
4. Sources are displayed separately so you can verify the response yourself

## Data Sources

- **Polymarket** - Prediction market odds and probabilities
- **The Guardian** - News articles
- **gov.uk** - Government press releases
- **FRED** - US economic indicators (Fed rate, CPI, VIX, oil, etc.)
- **Reddit** - Social sentiment from curated subreddits
