#!/usr/bin/env python3
"""
Build ChromaDB vector embeddings from existing data.

Loads markets, articles, and Reddit posts into ChromaDB for semantic search.

Usage:
    python scripts/build_embeddings.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.postgres import PostgresClient
from src.database.mongo import MongoDBClient
from src.database.chroma import ChromaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    pg = PostgresClient()
    chroma = ChromaClient()
    
    # 1. Load markets
    logger.info("Loading markets into ChromaDB...")
    markets = pg.get_markets(limit=1000)
    market_count = chroma.add_markets(markets)
    logger.info(f"  Added {market_count} markets")
    
    # 2. Load articles
    logger.info("Loading articles into ChromaDB...")
    articles = pg.get_articles(limit=2000)
    article_count = chroma.add_articles(articles)
    logger.info(f"  Added {article_count} articles")
    
    # 3. Load Reddit posts
    logger.info("Loading Reddit posts into ChromaDB...")
    try:
        mongo = MongoDBClient()
        mongo.connect()
        posts = mongo.get_posts(limit=3000)
        reddit_count = chroma.add_reddit_posts(posts)
        logger.info(f"  Added {reddit_count} Reddit posts")
        mongo.close()
    except Exception as e:
        logger.warning(f"  Could not load Reddit posts: {e}")
        reddit_count = 0
    
    # 4. Show stats
    stats = chroma.get_stats()
    logger.info(f"ChromaDB complete: {stats}")
    
    print(f"\nChromaDB embeddings built:")
    print(f"  Markets: {stats.get('markets', 0)}")
    print(f"  Articles: {stats.get('articles', 0)}")
    print(f"  Reddit: {stats.get('reddit', 0)}")
    print(f"  Total: {sum(stats.values())}")
    
    # 5. Test semantic search
    print("\nTest search - 'Iran conflict':")
    results = chroma.search_all("Iran conflict", n_results=5)
    for r in results:
        print(f"  [{r['collection']}] {r['document'][:60]}...")
        print(f"    Distance: {r['distance']:.3f}")


if __name__ == "__main__":
    main()
