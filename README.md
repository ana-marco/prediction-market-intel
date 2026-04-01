# Prediction Market Intelligence Agent

An AI agent that monitors prediction markets (Polymarket), combines them with news and economic data, and provides event risk intelligence.

**One-liner:** "What risks are prediction markets pricing right now, and what's driving them?"

## Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| Polymarket | REST API | Market odds and probabilities |
| Guardian | REST API | News articles |
| gov.uk | Web scraping | Government press releases |
| FRED | REST API | US economic indicators |
| Reddit | Public JSON | Social sentiment |

## Tech Stack

- **Databases:** PostgreSQL, MongoDB, Neo4j, ChromaDB
- **Agent Framework:** LangChain with MCP (langchain-mcp-adapters)
- **LLM:** Ollama (local, qwen2.5:7b)
- **MCP Server:** FastMCP with stdio transport
- **UI:** Chainlit

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- [Ollama](https://ollama.ai) (local LLM runtime)
- Free API keys: [Guardian](https://open-platform.theguardian.com/access/) and [FRED](https://fred.stlouisfed.org/docs/api/api_key.html)

## Quick Start (Makefile)

The fastest way to get running. Requires `make` (available via Git Bash on Windows).

```bash
# 1. Clone and configure
git clone <your-repo-url>
cd prediction-market-intel
cp .env.example .env
# Edit .env: add your GUARDIAN_API_KEY and FRED_API_KEY

# 2. Install dependencies and pull LLM model
make install

# 3. Load everything: databases, data, graph, embeddings
make setup

# 4. Start Ollama (in a separate terminal)
ollama serve

# 5. Run the agent
make run
```

Run `make help` to see all available targets.

## Manual Setup (step by step)

If `make` is not available, follow these steps.

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd prediction-market-intel
cp .env.example .env
# Edit .env: add your GUARDIAN_API_KEY and FRED_API_KEY
```

### 2. Create virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Pull the Ollama model

```bash
ollama pull qwen2.5:7b
```

### 4. Start databases

```bash
docker compose up -d
```

### 5. Initialize databases and load data

```bash
python scripts/run_pipeline.py
```

This runs all 8 pipeline steps in order: schema init, data loading (5 sources), graph build, and embeddings. It checks Docker containers are running before starting and stops on first failure.

Alternatively, run each step individually:

```bash
python scripts/init_db.py
python scripts/load_polymarket.py
python scripts/load_guardian.py
python scripts/load_govuk.py
python scripts/load_fred.py
python scripts/load_reddit.py
python scripts/build_graph.py
python scripts/build_embeddings.py
```

### 6. Start Ollama and run the agent

```bash
# In a separate terminal:
ollama serve

# Then run:
chainlit run src/ui/app.py
```

### 7. Run tests

```bash
make test
# Or without make:
PYTHONPATH=. python -m pytest tests/ -v
```

## Architecture

```
User Query (Chainlit UI)
        |
        v
Agent (LangChain + qwen2.5 via Ollama)
        |
  MCP stdio (JSON-RPC)
        |
   +---------+---------+
   v         v         v
MCP Tools  MCP Tools  RAG Tools
(LIVE)     (LIVE)     (HISTORICAL)
Polymarket  FRED      ChromaDB
Guardian    |         vectors
  |         |         |
  v (fallback)        v
PostgreSQL           Neo4j
MongoDB              (graph)
```

## Project Structure

```
prediction-market-intel/
├── src/
│   ├── ingestion/      # API clients and scrapers
│   ├── database/       # Storage layer (schema.sql, 4 DB clients)
│   ├── mcp/            # MCP server and 10 tools
│   ├── agent/          # LangChain agent
│   ├── utils/          # Shared utilities (topic extraction)
│   └── ui/             # Chainlit chat interface
├── scripts/            # Data loading and automation
├── tests/              # Unit, integration, and ingestion tests
├── data/cache/         # Cached API responses
└── docker-compose.yml  # 4 database containers
```

## Environment Variables

Copy `.env.example` to `.env`. Most variables have working defaults for local development. You only need to add your API keys.

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | PostgreSQL username | `pmi` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `pmi_dev_password` |
| `POSTGRES_DB` | PostgreSQL database name | `prediction_market_intel` |
| `POSTGRES_HOST` | PostgreSQL host | `127.0.0.1` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `MONGO_USER` | MongoDB username | `pmi` |
| `MONGO_PASSWORD` | MongoDB password | `pmi_dev_password` |
| `MONGO_HOST` | MongoDB host | `127.0.0.1` |
| `MONGO_PORT` | MongoDB port | `27017` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `pmi_dev_password` |
| `NEO4J_URI` | Neo4j bolt URI | `bolt://127.0.0.1:7687` |
| `CHROMA_HOST` | ChromaDB host | `127.0.0.1` |
| `CHROMA_PORT` | ChromaDB port | `8001` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| **`GUARDIAN_API_KEY`** | **Guardian API key ([get one](https://open-platform.theguardian.com/access/))** | **None (required)** |
| **`FRED_API_KEY`** | **FRED API key ([get one](https://fred.stlouisfed.org/docs/api/api_key.html))** | **None (required)** |
