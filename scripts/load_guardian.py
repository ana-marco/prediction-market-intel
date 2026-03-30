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
import re
import argparse
import logging
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.guardian import GuardianClient
from src.database.postgres import PostgresClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_topics_from_markets(db: PostgresClient, max_topics: int = 15) -> list[str]:
    """Extract search topics from loaded market questions."""
    
    markets = db.get_markets(limit=200)
    
    if not markets:
        logger.warning("No markets found. Using fallback topics.")
        return ["US politics", "world news", "economy", "trade", "climate"]
    
    # Common words to ignore
    stopwords = {
        "will", "the", "by", "in", "of", "to", "a", "an", "be", "is", "it",
        "for", "on", "at", "or", "and", "this", "that", "with", "as", "from",
        "before", "after", "during", "march", "april", "may", "june", "july",
        "2024", "2025", "2026", "2027", "2028", "yes", "no", "win", "lose",
        "happen", "end", "start", "over", "under", "more", "less", "than"
    }
    
    # Extract meaningful words from questions
    word_counts = Counter()
    
    for market in markets:
        question = market.get("question", "")
        # Extract capitalized words (likely proper nouns/topics)
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
        for word in words:
            if word.lower() not in stopwords and len(word) > 2:
                word_counts[word] += 1
        
        # Also extract quoted terms
        quoted = re.findall(r'"([^"]+)"', question)
        for term in quoted:
            if term.lower() not in stopwords:
                word_counts[term] += 1
    
    # Get top topics
    topics = [word for word, count in word_counts.most_common(max_topics)]
    
    logger.info(f"Extracted {len(topics)} topics from {len(markets)} markets")
    
    return topics


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
        topics = extract_topics_from_markets(db)
    
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
                    pass  # Duplicate or error, skip silently
            
            total += stored
            logger.info(f"  {topic}: {stored} articles stored")
            
        except Exception as e:
            logger.error(f"  {topic}: failed - {e}")
    
    logger.info(f"Total: {total} articles stored")
    
    # Show summary
    print(f"\nStored {total} Guardian articles across {len(topics)} topics")


if __name__ == "__main__":
    main()
