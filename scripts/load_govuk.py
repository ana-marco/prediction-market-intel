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
import re
import argparse
import logging
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.govuk_scraper import GovUKScraper
from src.database.postgres import PostgresClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_topics_from_markets(db: PostgresClient, max_topics: int = 10) -> list[str]:
    """Extract search topics from loaded market questions."""
    
    markets = db.get_markets(limit=200)
    
    if not markets:
        logger.warning("No markets found. Using fallback topics.")
        return ["foreign policy", "defence", "trade", "economy", "energy"]
    
    # Words to ignore
    stopwords = {
        "will", "the", "by", "in", "of", "to", "a", "an", "be", "is", "it",
        "for", "on", "at", "or", "and", "this", "that", "with", "as", "from",
        "before", "after", "during", "march", "april", "may", "june", "july",
        "2024", "2025", "2026", "2027", "2028", "yes", "no", "win", "lose",
        "happen", "end", "start", "over", "under", "more", "less", "than",
        "cup", "world", "fifa", "election", "president"  # Too US-specific for UK gov
    }
    
    # Extract meaningful words
    word_counts = Counter()
    
    for market in markets:
        question = market.get("question", "")
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
        for word in words:
            if word.lower() not in stopwords and len(word) > 2:
                word_counts[word] += 1
    
    # Map to UK-relevant search terms
    topic_mapping = {
        "Iran": "Iran",
        "China": "China trade",
        "Trump": "US relations",
        "NATO": "NATO defence",
        "Oil": "energy policy",
        "Bitcoin": "cryptocurrency",
        "Fed": "interest rates",
        "Trade": "trade policy",
    }
    
    topics = []
    for word, count in word_counts.most_common(20):
        if word in topic_mapping:
            topics.append(topic_mapping[word])
        elif count >= 2:  # Appears in multiple markets
            topics.append(word)
        
        if len(topics) >= max_topics:
            break
    
    # Always include some core UK policy areas
    core_topics = ["foreign policy", "defence", "economy"]
    for t in core_topics:
        if t not in topics and len(topics) < max_topics:
            topics.append(t)
    
    logger.info(f"Extracted {len(topics)} topics for gov.uk search")
    
    return topics


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
        topics = extract_topics_from_markets(db)
    
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
