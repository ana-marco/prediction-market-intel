#!/usr/bin/env python3
"""
Load press releases from gov.uk into PostgreSQL.

By default, extracts topics from loaded Polymarket markets.

Usage:
    python scripts/load_govuk.py
    python scripts/load_govuk.py --topics "Iran,defence,trade"
    python scripts/load_govuk.py --per-topic 30 --fetch-content
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.govuk_scraper import GovUKScraper
from src.database.postgres import PostgresClient
from src.utils.topic_extraction import extract_topics_from_markets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load gov.uk articles")
    parser.add_argument("--topics", type=str, help="Comma-separated topics")
    parser.add_argument("--per-topic", type=int, default=20, help="Articles per topic")
    parser.add_argument("--fetch-content", action="store_true", help="Fetch full article content (slower)")
    args = parser.parse_args()
    
    db = PostgresClient()
    
    # Get topics
    if args.topics:
        topics = [t.strip() for t in args.topics.split(",")]
    else:
        topics = extract_topics_from_markets(db, source="govuk")
    
    logger.info(f"Scraping gov.uk for {len(topics)} topics: {topics}")
    
    scraper = GovUKScraper()
    total = 0
    
    for topic in topics:
        try:
            articles = scraper.search_articles(
                keywords=topic,
                max_results=args.per_topic,
                fetch_content=args.fetch_content,
            )
            
            stored = 0
            for article in articles:
                try:
                    # Normalize for database
                    db_article = {
                        "id": article["url"],  # Use URL as unique ID
                        "title": article["title"],
                        "content": article.get("content"),
                        "summary": article.get("summary"),
                        "url": article["url"],
                        "published_at": article.get("published_at"),
                        "section": article.get("document_type"),
                        "author": article.get("organisation"),
                    }
                    db.insert_article(db_article, "govuk")
                    stored += 1
                except Exception as e:
                    logger.debug(f"Skipping article: {e}")
            
            total += stored
            logger.info(f"  {topic}: {stored} articles stored")
            
        except Exception as e:
            logger.error(f"  {topic}: failed - {e}")
    
    logger.info(f"Total: {total} gov.uk articles stored")
    print(f"\nStored {total} gov.uk articles across {len(topics)} topics")


if __name__ == "__main__":
    main()
