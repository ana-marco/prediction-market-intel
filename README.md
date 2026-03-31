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

### 4. Install Ollama model

```bash
ollama pull qwen2.5:7b
```

### 5. Initialize databases

```bash
python scripts/init_db.py
```

### 6. Load data

```bash
python scripts/load_polymarket.py
python scripts/load_guardian.py
python scripts/load_govuk.py
python scripts/load_fred.py
python scripts/load_reddit.py
python scripts/build_graph.py
python scripts/build_embeddings.py
```

### 7. Run the agent

```bash
chainlit run src/ui/app.py
```

### 8. Run tests

```bash
pytest tests/ -v
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
│   └── ui/             # Chainlit chat interface
├── scripts/            # Data loading and automation
├── tests/              # Unit and integration tests
├── data/cache/         # Cached API responses
└── docker-compose.yml  # 4 database containers
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_USER` | PostgreSQL username | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | Yes |
| `POSTGRES_DB` | PostgreSQL database name | Yes |
| `MONGO_USER` | MongoDB username | Yes |
| `MONGO_PASSWORD` | MongoDB password | Yes |
| `MONGO_HOST` | MongoDB host (default: `127.0.0.1`) | No |
| `MONGO_PORT` | MongoDB port (default: `27017`) | No |
| `NEO4J_USER` | Neo4j username | Yes |
| `NEO4J_PASSWORD` | Neo4j password | Yes |
| `NEO4J_URI` | Neo4j bolt URI (default: `bolt://127.0.0.1:7687`) | No |
| `GUARDIAN_API_KEY` | Guardian API key ([get one](https://open-platform.theguardian.com/access/)) | Yes |
| `FRED_API_KEY` | FRED API key ([get one](https://fred.stlouisfed.org/docs/api/api_key.html)) | Yes |
| `CHROMA_HOST` | ChromaDB host (default: `127.0.0.1`) | No |
| `CHROMA_PORT` | ChromaDB port (default: `8001`) | No |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) | No |
