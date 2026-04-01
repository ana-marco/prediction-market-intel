#!/usr/bin/env python3
"""
Load Reddit posts into MongoDB.

By default, browses subreddits AND searches for topics from loaded markets.

Usage:
    python scripts/load_reddit.py
    python scripts/load_reddit.py --subreddits wallstreetbets,economics
    python scripts/load_reddit.py --no-search  # Skip market topic search
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.reddit import RedditClient, DEFAULT_SUBREDDITS
from src.database.mongo import MongoDBClient
from src.database.postgres import PostgresClient
from src.utils.topic_extraction import extract_topics_from_markets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load Reddit posts into MongoDB")
    parser.add_argument("--subreddits", type=str, help="Comma-separated subreddit names")
    parser.add_argument("--limit", type=int, default=100, help="Posts per page (max 100)")
    parser.add_argument("--pages", type=int, default=3, help="Pages per subreddit (100 posts each)")
    parser.add_argument("--sort", type=str, default="hot", choices=["hot", "new", "top", "rising"])
    parser.add_argument("--time", type=str, default="week", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--no-search", action="store_true", help="Skip market topic search")
    args = parser.parse_args()
    
    # Initialize databases
    mongo = MongoDBClient()
    mongo.init_collections()
    
    reddit = RedditClient()
    total = 0
    
    # Part 1: Browse subreddits
    if args.subreddits:
        subreddits = [s.strip() for s in args.subreddits.split(",")]
    else:
        subreddits = DEFAULT_SUBREDDITS
    
    logger.info(f"Loading from {len(subreddits)} subreddits: {subreddits}")
    
    for sub in subreddits:
        try:
            posts = reddit.get_subreddit_posts(
                subreddit=sub,
                sort=args.sort,
                time_filter=args.time,
                limit=args.limit,
                max_pages=args.pages,
            )
            
            inserted = mongo.insert_posts(posts)
            total += inserted
            logger.info(f"  r/{sub}: {inserted} posts stored")
            
        except Exception as e:
            logger.error(f"  r/{sub}: failed - {e}")
    
    # Part 2: Search for market topics
    if not args.no_search:
        pg = PostgresClient()
        topics = extract_topics_from_markets(pg, source="reddit")
        
        if topics:
            logger.info(f"Searching Reddit for {len(topics)} market topics: {topics}")
            
            for topic in topics:
                try:
                    posts = reddit.search_posts(
                        query=topic,
                        sort="relevance",
                        time_filter=args.time,
                        limit=args.limit,
                    )
                    
                    inserted = mongo.insert_posts(posts)
                    total += inserted
                    logger.info(f"  Search '{topic}': {inserted} posts stored")
                    
                except Exception as e:
                    logger.error(f"  Search '{topic}': failed - {e}")
    
    # Show summary
    logger.info(f"Total: {total} posts stored in MongoDB")
    
    print(f"\nStored {total} Reddit posts")
    print("\nPosts by subreddit:")
    
    for stat in mongo.get_subreddit_stats():
        print(f"  r/{stat['_id']}: {stat['count']} posts (avg score: {stat['avg_score']:.0f})")
    
    mongo.close()


if __name__ == "__main__":
    main()
