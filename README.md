# Prediction Market Intelligence Agent

An AI agent that monitors prediction markets (Polymarket), combines them with news and economic data, and provides event risk intelligence.

**One-liner:** "What risks are prediction markets pricing right now, and what's driving them?"

## Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| Polymarket | REST API | Market odds and probabilities |
| Guardian | REST API | News articles |
| gov.uk | Web scraping | Government press releases |
| FRED | REST API + CSV | US economic indicators |
| Reddit | Public JSON | Social sentiment |

## Tech Stack

- **Databases:** PostgreSQL, MongoDB, Neo4j, ChromaDB
- **Agent Framework:** TBD (LangChain or OpenFang)
- **LLM:** Ollama (local)
- **UI:** Streamlit

## Setup

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd prediction-market-intel
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start databases

```bash
docker-compose up -d
```

### 3. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Initialize databases

```bash
python scripts/init_db.py
```

### 5. Load sample data

```bash
python scripts/load_sample_data.py
```

### 6. Run the agent

```bash
streamlit run src/ui/app.py
```

## Project Structure

```
prediction-market-intel/
├── src/
│   ├── ingestion/      # Data collection clients
│   ├── database/       # Storage layer
│   ├── mcp/            # MCP server and tools
│   ├── agent/          # Agent logic
│   └── ui/             # Streamlit app
├── scripts/            # Setup and automation
├── data/cache/         # Cached API responses
└── tests/
```

## API Keys Required

- Guardian API: https://open-platform.theguardian.com/access/
- FRED API: https://fred.stlouisfed.org/docs/api/api_key.html


