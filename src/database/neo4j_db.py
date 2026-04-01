"""
Neo4j Client

Handles graph database operations for relationships between:
- Markets (prediction markets)
- Articles (news from Guardian, gov.uk)
- Topics (extracted from market questions)
- Indicators (economic data from FRED)

Graph structure:
  (Market)-[:ABOUT]->(Topic)
  (Article)-[:COVERS]->(Topic)
  (Indicator)-[:MEASURES]->(Topic)
  (Market)-[:RELATED_TO]->(Article)
"""

import os
import logging
from datetime import datetime
from typing import Optional

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class Neo4jClient:
    """Client for Neo4j graph database operations."""
    
    def __init__(self):
        """Initialize Neo4j connection."""
        self.uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD")
        if not self.password:
            raise ValueError(
                "NEO4J_PASSWORD not set. Copy .env.example to .env and fill in credentials."
            )
        self.driver = None
    
    def connect(self):
        """Establish connection to Neo4j."""
        if self.driver is None:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            safe_uri = self.uri.split("@")[-1] if "@" in self.uri else self.uri
            logger.info(f"Connected to Neo4j at {safe_uri}")
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def init_schema(self):
        """Create indexes and constraints."""
        self.connect()
        
        with self.driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT market_id IF NOT EXISTS FOR (m:Market) REQUIRE m.id IS UNIQUE",
                "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
                "CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
                "CREATE CONSTRAINT indicator_id IF NOT EXISTS FOR (i:Indicator) REQUIRE i.series_id IS UNIQUE",
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    logger.debug(f"Constraint may already exist: {e}")
            
            indexes = [
                "CREATE INDEX market_question IF NOT EXISTS FOR (m:Market) ON (m.question)",
                "CREATE INDEX article_title IF NOT EXISTS FOR (a:Article) ON (a.title)",
                "CREATE INDEX topic_name_idx IF NOT EXISTS FOR (t:Topic) ON (t.name)",
            ]
            
            for index in indexes:
                try:
                    session.run(index)
                except Exception as e:
                    logger.debug(f"Index may already exist: {e}")
        
        logger.info("Neo4j schema initialized")
    
    def create_market(self, market: dict) -> None:
        """Create a Market node."""
        self.connect()
        
        query = """
        MERGE (m:Market {id: $id})
        SET m.question = $question,
            m.volume_24h = $volume_24h,
            m.outcome_prices = $outcome_prices,
            m.created_at = $created_at
        """
        
        # Convert Decimal to float for Neo4j compatibility
        volume = market.get("volume_24h", 0)
        if volume is not None:
            volume = float(volume)
        
        with self.driver.session() as session:
            session.run(query, {
                "id": market.get("id"),
                "question": market.get("question"),
                "volume_24h": volume,
                "outcome_prices": str(market.get("outcome_prices", {})),
                "created_at": datetime.now().isoformat(),
            })
    
    def create_article(self, article: dict) -> None:
        """Create an Article node."""
        self.connect()
        
        query = """
        MERGE (a:Article {id: $id})
        SET a.title = $title,
            a.source = $source,
            a.url = $url,
            a.published_at = $published_at
        """
        
        with self.driver.session() as session:
            session.run(query, {
                "id": article.get("id"),
                "title": article.get("title"),
                "source": article.get("source"),
                "url": article.get("url"),
                "published_at": article.get("published_at"),
            })
    
    def create_topic(self, name: str) -> None:
        """Create a Topic node."""
        self.connect()
        
        query = """
        MERGE (t:Topic {name: $name})
        SET t.created_at = $created_at
        """
        
        with self.driver.session() as session:
            session.run(query, {
                "name": name.lower(),
                "created_at": datetime.now().isoformat(),
            })
    
    def create_indicator(self, indicator: dict) -> None:
        """Create an Indicator node."""
        self.connect()
        
        query = """
        MERGE (i:Indicator {series_id: $series_id})
        SET i.name = $name,
            i.latest_value = $latest_value,
            i.latest_date = $latest_date
        """
        
        # Convert Decimal to float for Neo4j compatibility
        value = indicator.get("value")
        if value is not None:
            value = float(value)
        
        with self.driver.session() as session:
            session.run(query, {
                "series_id": indicator.get("series_id"),
                "name": indicator.get("name"),
                "latest_value": value,
                "latest_date": indicator.get("date"),
            })
    
    def link_market_to_topic(self, market_id: str, topic: str) -> None:
        """Create ABOUT relationship between Market and Topic."""
        self.connect()
        
        query = """
        MATCH (m:Market {id: $market_id})
        MERGE (t:Topic {name: $topic})
        MERGE (m)-[:ABOUT]->(t)
        """
        
        with self.driver.session() as session:
            session.run(query, {"market_id": market_id, "topic": topic.lower()})
    
    def link_article_to_topic(self, article_id: str, topic: str) -> None:
        """Create COVERS relationship between Article and Topic."""
        self.connect()
        
        query = """
        MATCH (a:Article {id: $article_id})
        MERGE (t:Topic {name: $topic})
        MERGE (a)-[:COVERS]->(t)
        """
        
        with self.driver.session() as session:
            session.run(query, {"article_id": article_id, "topic": topic.lower()})
    
    def link_indicator_to_topic(self, series_id: str, topic: str) -> None:
        """Create MEASURES relationship between Indicator and Topic."""
        self.connect()
        
        query = """
        MATCH (i:Indicator {series_id: $series_id})
        MERGE (t:Topic {name: $topic})
        MERGE (i)-[:MEASURES]->(t)
        """
        
        with self.driver.session() as session:
            session.run(query, {"series_id": series_id, "topic": topic.lower()})
    
    def get_market_context(self, market_id: str) -> dict:
        """
        Get all related content for a market.
        Returns articles, indicators, and other markets on same topics.
        """
        self.connect()
        
        query = """
        MATCH (m:Market {id: $market_id})-[:ABOUT]->(t:Topic)
        OPTIONAL MATCH (a:Article)-[:COVERS]->(t)
        OPTIONAL MATCH (i:Indicator)-[:MEASURES]->(t)
        OPTIONAL MATCH (other:Market)-[:ABOUT]->(t)
        WHERE other.id <> $market_id
        RETURN m.question as market,
               collect(DISTINCT t.name) as topics,
               collect(DISTINCT {title: a.title, source: a.source, url: a.url}) as articles,
               collect(DISTINCT {series_id: i.series_id, name: i.name, value: i.latest_value}) as indicators,
               collect(DISTINCT {id: other.id, question: other.question}) as related_markets
        """
        
        with self.driver.session() as session:
            result = session.run(query, {"market_id": market_id})
            record = result.single()
            
            if record:
                return {
                    "market": record["market"],
                    "topics": record["topics"],
                    "articles": [a for a in record["articles"] if a["title"]],
                    "indicators": [i for i in record["indicators"] if i["series_id"]],
                    "related_markets": [m for m in record["related_markets"] if m["id"]],
                }
            
            return None
    
    def search_by_topic(self, topic: str, limit: int = 10) -> dict:
        """Find all content related to a topic."""
        self.connect()
        
        query = """
        MATCH (t:Topic {name: $topic})
        OPTIONAL MATCH (m:Market)-[:ABOUT]->(t)
        OPTIONAL MATCH (a:Article)-[:COVERS]->(t)
        OPTIONAL MATCH (i:Indicator)-[:MEASURES]->(t)
        RETURN t.name as topic,
               collect(DISTINCT {id: m.id, question: m.question})[0..$limit] as markets,
               collect(DISTINCT {id: a.id, title: a.title, source: a.source})[0..$limit] as articles,
               collect(DISTINCT {series_id: i.series_id, name: i.name}) as indicators
        """
        
        with self.driver.session() as session:
            result = session.run(query, {"topic": topic.lower(), "limit": limit})
            record = result.single()
            
            if record:
                return {
                    "topic": record["topic"],
                    "markets": [m for m in record["markets"] if m["id"]],
                    "articles": [a for a in record["articles"] if a["id"]],
                    "indicators": [i for i in record["indicators"] if i["series_id"]],
                }
            
            return None
    
    def get_stats(self) -> dict:
        """Get graph statistics."""
        self.connect()
        
        query = """
        MATCH (m:Market) WITH count(m) as markets
        MATCH (a:Article) WITH markets, count(a) as articles
        MATCH (t:Topic) WITH markets, articles, count(t) as topics
        MATCH (i:Indicator) WITH markets, articles, topics, count(i) as indicators
        MATCH ()-[r]->() WITH markets, articles, topics, indicators, count(r) as relationships
        RETURN markets, articles, topics, indicators, relationships
        """
        
        with self.driver.session() as session:
            result = session.run(query)
            record = result.single()
            
            if record:
                return dict(record)
            
            return {}


def extract_topics_from_text(text: str) -> list[str]:
    """Extract topic keywords from text using substring matching.

    Uses a curated keyword-to-topic mapping (not NLP). Returns
    canonical topic names for use as Neo4j Topic node identifiers.
    """
    # Common topics to look for
    topic_keywords = {
        "iran": "iran",
        "iranian": "iran",
        "trump": "trump",
        "biden": "biden",
        "fed": "federal reserve",
        "federal reserve": "federal reserve",
        "interest rate": "interest rates",
        "inflation": "inflation",
        "cpi": "inflation",
        "oil": "oil",
        "crude": "oil",
        "bitcoin": "bitcoin",
        "crypto": "cryptocurrency",
        "china": "china",
        "chinese": "china",
        "russia": "russia",
        "russian": "russia",
        "ukraine": "ukraine",
        "nato": "nato",
        "election": "elections",
        "tariff": "tariffs",
        "trade war": "trade",
        "recession": "recession",
        "gdp": "gdp",
        "unemployment": "unemployment",
        "stock": "stock market",
        "s&p": "stock market",
    }
    
    text_lower = text.lower()
    found_topics = set()
    
    for keyword, topic in topic_keywords.items():
        if keyword in text_lower:
            found_topics.add(topic)
    
    return list(found_topics)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    with Neo4jClient() as neo4j:
        neo4j.init_schema()
        stats = neo4j.get_stats()
        print(f"Graph stats: {stats}")
