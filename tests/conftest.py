"""
Shared test fixtures and markers.

Integration test fixtures connect to real Docker databases.
Tests are skipped if the database is unavailable.

Usage:
    pytest tests/ -v                          # all tests
    pytest tests/ -m "not integration" -v     # unit tests only
    pytest tests/ -m integration -v           # integration only
    pytest tests/ --cov=src --cov-report=term # with coverage
"""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: requires Docker databases"
    )
    config.addinivalue_line(
        "markers",
        "agent_eval: end-to-end agent runs against the live LLM "
        "(slow, ~30-60s per test, run on demand via pytest -m agent_eval)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip agent_eval tests unless `-m agent_eval` is passed."""
    selected = config.getoption("-m") or ""
    if "agent_eval" in selected:
        return

    skip = pytest.mark.skip(reason="run with `pytest -m agent_eval`")
    for item in items:
        if "agent_eval" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def db():
    """PostgresClient connected to the Docker database."""
    from src.database.postgres import PostgresClient

    client = PostgresClient()
    try:
        with client.get_cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("PostgreSQL not available")
    return client


@pytest.fixture
def chroma():
    """ChromaClient connected to the Docker database."""
    from src.database.chroma import ChromaClient

    client = ChromaClient()
    try:
        client.connect()
    except Exception:
        pytest.skip("ChromaDB not available")
    return client


@pytest.fixture
def mongo():
    """MongoDBClient connected to the Docker database."""
    from src.database.mongo import MongoDBClient

    client = MongoDBClient()
    try:
        client.connect()
    except Exception:
        pytest.skip("MongoDB not available")
    return client


@pytest.fixture
def neo4j_client():
    """Neo4jClient connected to the Docker database."""
    from src.database.neo4j_db import Neo4jClient

    client = Neo4jClient()
    try:
        client.connect()
    except Exception:
        pytest.skip("Neo4j not available")
    yield client
    client.close()
