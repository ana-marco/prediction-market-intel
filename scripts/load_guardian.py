#!/usr/bin/env python3
"""
Load news articles from The Guardian into PostgreSQL.

By default, extracts topics from loaded Polymarket markets.

Usage:
    python scripts/load_guardian.py
    python scripts/load_guardian.py --topics "Iran,China,tariffs"
    python scripts/load_guardian.py --days 7 --per-topic 50
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.guardian import GuardianClient
from src.database.postgres import PostgresClient
from src.utils.topic_extraction import extract_topics_from_markets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load Guardian articles")
    parser.add_argument("--topics", type=str, help="Comma-separated topics (default: extract from markets)")
    parser.add_argument("--days", type=int, default=14, help="Days back to search")
    parser.add_argument("--per-topic", type=int, default=30, help="Articles per topic")
    args = parser.parse_args()
    
    db = PostgresClient()
    
    # Get topics from argument or extract from markets
    if args.topics:
        topics = [t.strip() for t in args.topics.split(",")]
    else:
        topics = extract_topics_from_markets(db, source="guardian", max_topics=15)
    
    logger.info(f"Loading articles for {len(topics)} topics: {topics}")
    
    g = GuardianClient()
    total = 0
    
    for topic in topics:
        try:
            articles = g.search_articles(
                topic.strip(), 
                days_back=args.days, 
                max_results=args.per_topic
            )
            
            stored = 0
            for article in articles:
                try:
                    db.insert_article(article, "guardian")
                    stored += 1
                except Exception as e:
                    logger.debug(f"Skipping article: {e}")
            
            total += stored
            logger.info(f"  {topic}: {stored} articles stored")
            
        except Exception as e:
            logger.error(f"  {topic}: failed - {e}")
    
    logger.info(f"Total: {total} articles stored")
    
    # Show summary
    print(f"\nStored {total} Guardian articles across {len(topics)} topics")


if __name__ == "__main__":
    main()
