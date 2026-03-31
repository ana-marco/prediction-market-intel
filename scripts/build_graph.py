#!/usr/bin/env python3
"""
Build Neo4j graph from existing PostgreSQL and MongoDB data.

Creates nodes and relationships:
- Markets -> Topics
- Articles -> Topics  
- Indicators -> Topics

Usage:
    python scripts/build_graph.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.postgres import PostgresClient
from src.database.mongo import MongoDBClient
from src.database.neo4j_db import Neo4jClient, extract_topics_from_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Map FRED indicators to topics
INDICATOR_TOPICS = {
    "FEDFUNDS": ["federal reserve", "interest rates"],
    "CPIAUCSL": ["inflation"],
    "UNRATE": ["unemployment"],
    "DCOILWTICO": ["oil"],
    "DGS10": ["interest rates", "bonds"],
    "VIXCLS": ["stock market", "volatility"],
    "DTWEXBGS": ["trade", "currency"],
    "T10Y2Y": ["interest rates", "recession"],
}


def main():
    pg = PostgresClient()
    neo4j = Neo4jClient()
    
    # Initialize schema
    neo4j.init_schema()
    
    # 1. Load markets and extract topics
    logger.info("Loading markets into graph...")
    markets = pg.get_markets(limit=1000)
    market_count = 0
    
    for market in markets:
        try:
            neo4j.create_market(market)
            topics = extract_topics_from_text(market.get("question", ""))
            for topic in topics:
                neo4j.link_market_to_topic(market["id"], topic)
            market_count += 1
        except Exception as e:
            logger.debug(f"Skipping market {market.get('id')}: {e}")
    
    logger.info(f"  Loaded {market_count} markets")
    
    # 2. Load articles and extract topics
    logger.info("Loading articles into graph...")
    articles = pg.get_articles(limit=2000)
    article_count = 0
    
    for article in articles:
        try:
            article_id = article.get("external_id") or str(article.get("id"))
            neo4j.create_article({
                "id": article_id,
                "title": article.get("title"),
                "source": article.get("source"),
                "url": article.get("url"),
                "published_at": str(article.get("published_at")) if article.get("published_at") else None,
            })
            text = f"{article.get('title', '')} {article.get('content', '')}"
            topics = extract_topics_from_text(text)
            for topic in topics:
                neo4j.link_article_to_topic(article_id, topic)
            article_count += 1
        except Exception as e:
            logger.debug(f"Skipping article {article.get('id')}: {e}")
    
    logger.info(f"  Loaded {article_count} articles")
    
    # 3. Load indicators and link to topics
    logger.info("Loading indicators into graph...")
    indicator_count = 0
    
    for series_id, topics in INDICATOR_TOPICS.items():
        latest = pg.get_latest_indicator(series_id)
        if latest:
            neo4j.create_indicator({
                "series_id": series_id,
                "name": latest.get("name") or series_id,
                "value": latest.get("value"),
                "date": str(latest.get("date")),
            })
            
            for topic in topics:
                neo4j.link_indicator_to_topic(series_id, topic)
            
            indicator_count += 1
    
    logger.info(f"  Loaded {indicator_count} indicators")
    
    # 4. Show stats
    stats = neo4j.get_stats()
    logger.info(f"Graph complete: {stats}")
    
    print(f"\nNeo4j graph built:")
    print(f"  Markets: {stats.get('markets', 0)}")
    print(f"  Articles: {stats.get('articles', 0)}")
    print(f"  Topics: {stats.get('topics', 0)}")
    print(f"  Indicators: {stats.get('indicators', 0)}")
    print(f"  Relationships: {stats.get('relationships', 0)}")
    
    # 5. Test a query
    print("\nTest query - content about 'iran':")
    result = neo4j.search_by_topic("iran", limit=3)
    if result:
        print(f"  Markets: {len(result.get('markets', []))}")
        print(f"  Articles: {len(result.get('articles', []))}")
        if result.get('markets'):
            print(f"  Example: {result['markets'][0].get('question', '')[:60]}...")
    
    neo4j.close()


if __name__ == "__main__":
    main()
