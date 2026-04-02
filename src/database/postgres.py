"""
PostgreSQL Database Client

Handles connection and operations for structured data:
- Markets (Polymarket)
- Articles (Guardian, gov.uk)
- Economic indicators (FRED)
- Data lineage tracking
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Schema file location
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class PostgresClient:
    """Client for PostgreSQL database operations."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
    ):
        self.config = {
            "host": host or os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "port": port or int(os.getenv("POSTGRES_PORT", "5432")),
            "database": database or os.getenv("POSTGRES_DB", "prediction_market_intel"),
            "user": user or os.getenv("POSTGRES_USER", "pmi"),
            "password": password or os.getenv("POSTGRES_PASSWORD"),
        }
        if not self.config["password"]:
            raise ValueError(
                "POSTGRES_PASSWORD not set. Copy .env.example to .env and fill in credentials."
            )
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = psycopg2.connect(**self.config)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    @contextmanager
    def get_cursor(self, dict_cursor: bool = True):
        """Context manager for database cursors."""
        with self.get_connection() as conn:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()
    
    def init_schema(self) -> None:
        """Initialize database schema from SQL file."""
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
        
        with open(SCHEMA_PATH, "r") as f:
            schema_sql = f.read()
        
        with self.get_cursor() as cursor:
            cursor.execute(schema_sql)
        
        logger.info("Database schema initialized")
    
    # Market upserts and queries

    def upsert_market(self, market: dict) -> str:
        """Insert or update a market record."""
        if not market.get("id") or not market.get("question"):
            raise ValueError("Market missing required fields: id, question")
        sql = """
            INSERT INTO markets (
                id, question, description, outcome_prices, outcomes,
                volume_24h, liquidity, start_date, end_date, status,
                category, tags, source_url, raw_data
            ) VALUES (
                %(id)s, %(question)s, %(description)s, %(outcome_prices)s, %(outcomes)s,
                %(volume_24h)s, %(liquidity)s, %(start_date)s, %(end_date)s, %(status)s,
                %(category)s, %(tags)s, %(source_url)s, %(raw_data)s
            )
            ON CONFLICT (id) DO UPDATE SET
                question = EXCLUDED.question,
                description = EXCLUDED.description,
                outcome_prices = EXCLUDED.outcome_prices,
                volume_24h = EXCLUDED.volume_24h,
                liquidity = EXCLUDED.liquidity,
                status = EXCLUDED.status,
                raw_data = EXCLUDED.raw_data,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        # Map camelCase API fields to snake_case DB columns
        params = {
            "id": market.get("id") or market.get("condition_id"),
            "question": market.get("question"),
            "description": market.get("description"),
            "outcome_prices": Json(market.get("outcomePrices")),
            "outcomes": Json(market.get("outcomes")),
            "volume_24h": market.get("volume24hr") or market.get("volume_24h"),
            "liquidity": market.get("liquidity"),
            "start_date": market.get("startDate") or market.get("start_date"),
            "end_date": market.get("endDate") or market.get("end_date"),
            "status": "active" if market.get("active") else "closed",
            "category": market.get("category"),
            "tags": market.get("tags"),
            "source_url": f"https://polymarket.com/event/{market.get('slug', '')}",
            "raw_data": Json(market),
        }
        
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            market_id = result["id"] if result else params["id"]
        
        self._record_lineage("markets", market_id, "polymarket", market,
                             "camelCase to snake_case field mapping, "
                             "outcomePrices JSON string to JSONB, "
                             "active/closed boolean to status string, "
                             "slug to source_url construction")
        
        return market_id
    
    def upsert_markets(self, markets: list[dict]) -> int:
        """Bulk insert/update markets. Returns count."""
        count = 0
        for market in markets:
            try:
                self.upsert_market(market)
                count += 1
            except Exception as e:
                logger.error(f"Failed to upsert market {market.get('id')}: {e}")
        return count
    
    def get_market(self, market_id: str) -> Optional[dict]:
        """Get a single market by ID."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM markets WHERE id = %s", (market_id,))
            return cursor.fetchone()
    
    def get_markets(
        self,
        status: str = None,
        category: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query markets with optional filters."""
        sql = "SELECT * FROM markets WHERE 1=1"
        params = []
        
        if status:
            sql += " AND status = %s"
            params.append(status)
        
        if category:
            sql += " AND category = %s"
            params.append(category)
        
        sql += " ORDER BY volume_24h DESC NULLS LAST LIMIT %s"
        params.append(limit)
        
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    
    def search_markets(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search on market questions."""
        sql = """
            SELECT *, ts_rank(to_tsvector('english', question), query) as rank
            FROM markets, plainto_tsquery('english', %s) query
            WHERE to_tsvector('english', question) @@ query
            ORDER BY rank DESC
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (query, limit))
            return cursor.fetchall()
    
    # Article inserts and search
    
    def insert_article(self, article: dict, source: str) -> int:
        """Insert a news article. Returns article ID."""
        title = article.get("title") or article.get("webTitle")
        if not title or not source:
            raise ValueError("Article missing required fields: title, source")
        sql = """
            INSERT INTO articles (
                source, external_id, title, content, summary,
                url, published_at, author, section, tags, raw_data
            ) VALUES (
                %(source)s, %(external_id)s, %(title)s, %(content)s, %(summary)s,
                %(url)s, %(published_at)s, %(author)s, %(section)s, %(tags)s, %(raw_data)s
            )
            ON CONFLICT (source, external_id) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                raw_data = EXCLUDED.raw_data
            RETURNING id
        """
        
        params = {
            "source": source,
            "external_id": article.get("id") or article.get("external_id"),
            "title": article.get("title") or article.get("webTitle"),
            "content": article.get("content") or article.get("body"),
            "summary": article.get("summary") or article.get("standfirst"),
            "url": article.get("url") or article.get("webUrl"),
            "published_at": article.get("published_at") or article.get("webPublicationDate"),
            "author": article.get("author"),
            "section": article.get("section") or article.get("sectionName"),
            "tags": article.get("tags"),
            "raw_data": Json(article),
        }
        
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            article_id = result["id"] if result else None
        
        self._record_lineage("articles", str(article_id), source, article,
                             f"field normalisation from {source}: "
                             "nested fields flattened (headline/webTitle to title, "
                             "body/standfirst to content/summary), "
                             "HTML extracted for govuk source")
        return article_id
    
    def get_articles(
        self,
        source: str = None,
        section: str = None,
        since: datetime = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query articles with optional filters."""
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []
        
        if source:
            sql += " AND source = %s"
            params.append(source)
        
        if section:
            sql += " AND section = %s"
            params.append(section)
        
        if since:
            sql += " AND published_at >= %s"
            params.append(since)
        
        sql += " ORDER BY published_at DESC LIMIT %s"
        params.append(limit)
        
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    
    def search_articles(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search on articles."""
        sql = """
            SELECT *, ts_rank(
                to_tsvector('english', title || ' ' || COALESCE(content, '')), 
                query
            ) as rank
            FROM articles, plainto_tsquery('english', %s) query
            WHERE to_tsvector('english', title || ' ' || COALESCE(content, '')) @@ query
            ORDER BY rank DESC
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (query, limit))
            return cursor.fetchall()
    
    # Economic indicator storage and retrieval
    
    def insert_indicator(
        self,
        series_id: str,
        name: str,
        value: float,
        date: str,
        unit: str = None,
        frequency: str = None,
    ) -> int:
        """Insert an economic indicator data point."""
        if not series_id or not date:
            raise ValueError("Indicator missing required fields: series_id, date")
        sql = """
            INSERT INTO economic_indicators (
                series_id, name, value, date, unit, frequency
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (series_id, date) DO UPDATE SET
                value = EXCLUDED.value
            RETURNING id
        """
        
        with self.get_cursor() as cursor:
            cursor.execute(sql, (series_id, name, value, date, unit, frequency))
            result = cursor.fetchone()
            indicator_id = result["id"]

        self._record_lineage(
            "economic_indicators", str(indicator_id), "fred",
            {"series_id": series_id, "name": name, "value": str(value),
             "date": str(date), "unit": unit, "frequency": frequency},
            "two API calls merged (series metadata + observations), "
            "missing value marker '.' converted to None, "
            "string values cast to float"
        )
        return indicator_id
    
    def get_latest_indicator(self, series_id: str) -> Optional[dict]:
        """Get most recent value for an indicator."""
        sql = """
            SELECT * FROM economic_indicators 
            WHERE series_id = %s 
            ORDER BY date DESC 
            LIMIT 1
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (series_id,))
            return cursor.fetchone()
    
    def get_indicator_history(
        self,
        series_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """Get historical values for an indicator."""
        sql = """
            SELECT * FROM economic_indicators 
            WHERE series_id = %s 
            ORDER BY date DESC 
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (series_id, limit))
            return cursor.fetchall()
    
    # Data lineage tracking (provenance and checksums)
    
    def _record_lineage(
        self,
        table_name: str,
        record_id: str,
        source: str,
        raw_data: dict,
        transformation: str = None,
    ) -> None:
        """Record data lineage for a record."""
        sql = """
            INSERT INTO data_lineage (
                table_name, record_id, source, fetched_at,
                transformation, checksum, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_name, record_id, fetched_at) DO NOTHING
        """

        # sort_keys ensures identical data always produces the same checksum
        checksum = hashlib.sha256(
            json.dumps(raw_data, sort_keys=True).encode()
        ).hexdigest()

        try:
            with self.get_cursor() as cursor:
                cursor.execute(sql, (
                    table_name,
                    record_id,
                    source,
                    datetime.now(),
                    transformation,
                    checksum,
                    Json({"keys": list(raw_data.keys()) if raw_data else []}),
                ))
        except Exception as e:
            logger.warning(f"Failed to record lineage: {e}")
    
    def get_lineage(self, table_name: str, record_id: str) -> list[dict]:
        """Get lineage history for a record."""
        sql = """
            SELECT * FROM data_lineage 
            WHERE table_name = %s AND record_id = %s 
            ORDER BY fetched_at DESC
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (table_name, record_id))
            return cursor.fetchall()


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    db = PostgresClient()
    
    print("Initializing schema...")
    db.init_schema()
    print("Schema initialized successfully!")
    
    # Test with sample data
    sample_market = {
        "id": "test-123",
        "question": "Will it rain tomorrow?",
        "outcomePrices": {"Yes": "0.65", "No": "0.35"},
        "volume24hr": 10000,
        "active": True,
    }
    
    market_id = db.upsert_market(sample_market)
    print(f"Inserted market: {market_id}")
    
    retrieved = db.get_market(market_id)
    print(f"Retrieved: {retrieved['question']}")
