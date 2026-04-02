#!/usr/bin/env python3
"""
Load prediction markets from Polymarket into PostgreSQL.

Usage:
    python scripts/load_polymarket.py
    python scripts/load_polymarket.py --limit 200
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.polymarket import PolymarketClient
from src.database.postgres import PostgresClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load Polymarket data")
    parser.add_argument("--limit", type=int, default=100, help="Number of markets to fetch")
    parser.add_argument("--use-cache", action="store_true", help="Use cached data if available")
    args = parser.parse_args()
    
    logger.info(f"Fetching up to {args.limit} markets from Polymarket...")
    
    pm = PolymarketClient(use_cache=args.use_cache)
    try:
        markets = pm.get_markets(limit=args.limit)
    except Exception as e:
        logger.error(f"Failed to fetch markets from Polymarket: {e}")
        sys.exit(1)

    logger.info(f"Fetched {len(markets)} markets")

    db = PostgresClient()
    try:
        count = db.upsert_markets(markets)
    except Exception as e:
        logger.error(f"Failed to store markets in PostgreSQL: {e}")
        sys.exit(1)
    
    logger.info(f"Stored {count} markets in PostgreSQL")
    
    # Show top 5
    print("\nTop 5 markets by 24h volume:")
    top = db.get_markets(limit=5)
    for m in top:
        vol = f"${m['volume_24h']:,.0f}" if m['volume_24h'] else "N/A"
        print(f"  {m['question'][:70]}")
        print(f"    Volume: {vol}")


if __name__ == "__main__":
    main()
