"""
Polymarket API Client

Fetches prediction market data from Polymarket's Gamma API.
Docs: https://docs.polymarket.com/

Supports both live fetching and cached data for reliable demos.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Polymarket Gamma API endpoints
BASE_URL = "https://gamma-api.polymarket.com"

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


class PolymarketClient:
    """Client for fetching prediction market data from Polymarket."""
    
    def __init__(self, use_cache: bool = True, cache_ttl_hours: int = 1):
        """
        Args:
            use_cache: If True, return cached data when available
            cache_ttl_hours: How long cached data is considered fresh
        """
        self.use_cache = use_cache
        self.cache_ttl_hours = cache_ttl_hours
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "UCL-MSIN0166-Project/1.0"
        })
        
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def get_markets(
        self,
        limit: int = 100,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[dict]:
        """
        Fetch list of prediction markets.
        
        Args:
            limit: Maximum number of markets to return
            active: Include active markets
            closed: Include closed markets
            order: Sort field (volume24hr, liquidity, startDate, endDate)
            ascending: Sort direction
            
        Returns:
            List of market dictionaries
        """
        cache_key = f"markets_{limit}_{active}_{closed}_{order}"
        
        # Try cache first
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached data for {cache_key}")
                return cached
        
        # Fetch from API
        try:
            params = {
                "limit": limit,
                "active": str(active).lower(),
                "closed": str(closed).lower(),
                "order": order,
                "ascending": str(ascending).lower(),
            }
            
            response = self.session.get(f"{BASE_URL}/markets", params=params)
            response.raise_for_status()
            
            markets = response.json()
            
            # Cache the response
            self._write_cache(cache_key, markets)
            
            logger.info(f"Fetched {len(markets)} markets from Polymarket API")
            return markets
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch markets: {e}")
            
            # Fall back to cache even if expired
            cached = self._read_cache(cache_key, ignore_ttl=True)
            if cached:
                logger.warning("Using expired cache as fallback")
                return cached
            
            raise
    
    def get_market(self, market_id: str) -> Optional[dict]:
        """
        Fetch a single market by ID.
        
        Args:
            market_id: The market's condition_id or slug
            
        Returns:
            Market dictionary or None if not found
        """
        cache_key = f"market_{market_id}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                return cached
        
        try:
            response = self.session.get(f"{BASE_URL}/markets/{market_id}")
            response.raise_for_status()
            
            market = response.json()
            self._write_cache(cache_key, market)
            
            return market
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return self._read_cache(cache_key, ignore_ttl=True)
    
    def search_markets(self, query: str, limit: int = 20) -> list[dict]:
        """
        Search markets by keyword.
        
        Args:
            query: Search term
            limit: Maximum results
            
        Returns:
            List of matching markets
        """
        cache_key = f"search_{query}_{limit}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                return cached
        
        try:
            params = {"query": query, "limit": limit}
            response = self.session.get(f"{BASE_URL}/markets", params=params)
            response.raise_for_status()
            
            markets = response.json()
            self._write_cache(cache_key, markets)
            
            return markets
            
        except requests.RequestException as e:
            logger.error(f"Failed to search markets for '{query}': {e}")
            return self._read_cache(cache_key, ignore_ttl=True) or []
    
    def get_events(self, limit: int = 50) -> list[dict]:
        """
        Fetch events (groups of related markets).
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of event dictionaries
        """
        cache_key = f"events_{limit}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                return cached
        
        try:
            params = {"limit": limit}
            response = self.session.get(f"{BASE_URL}/events", params=params)
            response.raise_for_status()
            
            events = response.json()
            self._write_cache(cache_key, events)
            
            return events
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch events: {e}")
            return self._read_cache(cache_key, ignore_ttl=True) or []
    
    def _cache_path(self, key: str) -> Path:
        """Get path for a cache key."""
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return CACHE_DIR / f"polymarket_{safe_key}.json"
    
    def _read_cache(self, key: str, ignore_ttl: bool = False) -> Optional[list | dict]:
        """Read data from cache if fresh."""
        path = self._cache_path(key)
        
        if not path.exists():
            return None
        
        try:
            with open(path, "r") as f:
                cached = json.load(f)
            
            # Check freshness
            if not ignore_ttl:
                cached_at = datetime.fromisoformat(cached["cached_at"])
                age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                
                if age_hours > self.cache_ttl_hours:
                    return None
            
            return cached["data"]
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid cache file {path}: {e}")
            return None
    
    def _write_cache(self, key: str, data: list | dict) -> None:
        """Write data to cache."""
        path = self._cache_path(key)
        
        try:
            with open(path, "w") as f:
                json.dump({
                    "cached_at": datetime.now().isoformat(),
                    "data": data
                }, f, indent=2)
        except IOError as e:
            logger.warning(f"Failed to write cache {path}: {e}")


# Convenience function for quick testing
def fetch_top_markets(n: int = 10) -> list[dict]:
    """Fetch top N markets by 24h volume."""
    client = PolymarketClient()
    markets = client.get_markets(limit=n)
    
    # Extract key info
    return [
        {
            "id": m.get("id"),
            "question": m.get("question"),
            "outcome_prices": m.get("outcomePrices"),
            "volume_24h": m.get("volume24hr"),
            "liquidity": m.get("liquidity"),
            "end_date": m.get("endDate"),
        }
        for m in markets
    ]


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching top markets from Polymarket...")
    markets = fetch_top_markets(5)
    
    for m in markets:
        print(f"\n{m['question']}")
        print(f"  Prices: {m['outcome_prices']}")
        print(f"  24h Volume: ${m['volume_24h']:,.0f}" if m['volume_24h'] else "  24h Volume: N/A")
