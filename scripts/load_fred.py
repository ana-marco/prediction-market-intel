#!/usr/bin/env python3
"""
Load economic indicators from FRED into PostgreSQL.

Usage:
    python scripts/load_fred.py
    python scripts/load_fred.py --history 365
    python scripts/load_fred.py --series FEDFUNDS,CPIAUCSL
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.fred import FREDClient, DEFAULT_SERIES
from src.database.postgres import PostgresClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load FRED economic indicators")
    parser.add_argument("--series", type=str, help="Comma-separated series IDs (default: key indicators)")
    parser.add_argument("--history", type=int, default=365, help="Days of history to fetch")
    parser.add_argument("--latest-only", action="store_true", help="Only fetch latest values")
    args = parser.parse_args()
    
    # Get series to fetch
    if args.series:
        series_ids = [s.strip() for s in args.series.split(",")]
    else:
        series_ids = list(DEFAULT_SERIES.keys())
    
    logger.info(f"Loading {len(series_ids)} indicators from FRED")
    
    fred = FREDClient()
    db = PostgresClient()
    
    total = 0
    
    for series_id in series_ids:
        try:
            if args.latest_only:
                # Just get latest value
                latest = fred.get_latest(series_id)
                if latest and latest["value"] is not None:
                    db.insert_indicator(
                        series_id=latest["series_id"],
                        name=latest["name"],
                        value=latest["value"],
                        date=latest["date"],
                        unit=latest.get("units"),
                        frequency=latest.get("frequency"),
                    )
                    total += 1
                    logger.info(f"  {series_id}: {latest['value']} ({latest['date']})")
            else:
                # Get historical data
                history = fred.get_series_history(series_id, days_back=args.history)
                
                stored = 0
                for obs in history:
                    if obs["value"] is not None:
                        try:
                            db.insert_indicator(
                                series_id=obs["series_id"],
                                name=obs["name"],
                                value=obs["value"],
                                date=obs["date"],
                                unit=obs.get("units"),
                            )
                            stored += 1
                        except Exception:
                            pass  # Duplicate
                
                total += stored
                logger.info(f"  {series_id}: {stored} observations stored")
                
        except Exception as e:
            logger.error(f"  {series_id}: failed - {e}")
    
    logger.info(f"Total: {total} indicator values stored")
    
    # Show summary
    print(f"\nStored {total} economic indicator values")
    print("\nLatest values:")
    
    for series_id in series_ids[:5]:  # Show first 5
        latest = db.get_latest_indicator(series_id)
        if latest:
            print(f"  {series_id}: {latest['value']} ({latest['date']})")


if __name__ == "__main__":
    main()
