"""
FRED API Client

Fetches economic indicators from the Federal Reserve Economic Data API.
Docs: https://fred.stlouisfed.org/docs/api/fred/

Key indicators for prediction markets:
- FEDFUNDS: Federal funds rate
- CPIAUCSL: Consumer Price Index (inflation)
- UNRATE: Unemployment rate
- DCOILWTICO: WTI crude oil price
- DGS10: 10-year Treasury rate
- SP500: S&P 500 index
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = "https://api.stlouisfed.org/fred"

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

# Key economic indicators relevant to prediction markets
DEFAULT_SERIES = {
    "FEDFUNDS": "Federal Funds Effective Rate",
    "CPIAUCSL": "Consumer Price Index (All Urban Consumers)",
    "UNRATE": "Unemployment Rate",
    "DCOILWTICO": "Crude Oil Prices: WTI",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "VIXCLS": "CBOE Volatility Index (VIX)",
    "DTWEXBGS": "Trade Weighted US Dollar Index",
    "T10Y2Y": "10-Year Treasury Minus 2-Year (Yield Curve)",
}


class FREDClient:
    """Client for fetching economic data from FRED."""
    
    def __init__(self, api_key: str = None, use_cache: bool = True, cache_ttl_hours: int = 6):
        """
        Args:
            api_key: FRED API key (defaults to FRED_API_KEY env var)
            use_cache: If True, return cached data when available
            cache_ttl_hours: How long cached data is considered fresh
        """
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("FRED API key required. Set FRED_API_KEY in .env")
        
        self.use_cache = use_cache
        self.cache_ttl_hours = cache_ttl_hours
        self.session = requests.Session()
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def get_series(
        self,
        series_id: str,
        start_date: str = None,
        end_date: str = None,
        limit: int = 100,
    ) -> dict:
        """
        Fetch data for a FRED series.
        
        Args:
            series_id: FRED series ID (e.g., "FEDFUNDS")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            limit: Maximum observations to return
            
        Returns:
            Dict with series info and observations
        """
        cache_key = f"fred_{series_id}_{start_date}_{end_date}_{limit}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached FRED data for {series_id}")
                return cached
        
        try:
            # Get series info
            info_params = {
                "api_key": self.api_key,
                "series_id": series_id,
                "file_type": "json",
            }
            info_response = self.session.get(f"{BASE_URL}/series", params=info_params)
            info_response.raise_for_status()
            series_info = info_response.json().get("seriess", [{}])[0]
            
            # Get observations
            obs_params = {
                "api_key": self.api_key,
                "series_id": series_id,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            }
            
            if start_date:
                obs_params["observation_start"] = start_date
            if end_date:
                obs_params["observation_end"] = end_date
            
            obs_response = self.session.get(f"{BASE_URL}/series/observations", params=obs_params)
            obs_response.raise_for_status()
            observations = obs_response.json().get("observations", [])
            
            result = {
                "series_id": series_id,
                "title": series_info.get("title"),
                "units": series_info.get("units"),
                "frequency": series_info.get("frequency"),
                "observations": observations,
            }
            
            self._write_cache(cache_key, result)
            
            logger.info(f"Fetched {len(observations)} observations for {series_id}")
            return result
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch FRED series {series_id}: {e}")
            
            cached = self._read_cache(cache_key, ignore_ttl=True)
            if cached:
                logger.warning("Using expired cache as fallback")
                return cached
            
            raise
    
    def get_latest(self, series_id: str) -> Optional[dict]:
        """
        Get the most recent value for a series.
        
        Args:
            series_id: FRED series ID
            
        Returns:
            Dict with date, value, and series info
        """
        data = self.get_series(series_id, limit=1)
        
        if not data.get("observations"):
            return None
        
        obs = data["observations"][0]
        
        return {
            "series_id": series_id,
            "name": data.get("title"),
            "value": float(obs["value"]) if obs["value"] != "." else None,
            "date": obs["date"],
            "units": data.get("units"),
            "frequency": data.get("frequency"),
        }
    
    def get_all_indicators(self, series_ids: list[str] = None) -> list[dict]:
        """
        Fetch latest values for multiple indicators.
        
        Args:
            series_ids: List of series IDs (defaults to DEFAULT_SERIES)
            
        Returns:
            List of indicator dicts
        """
        if series_ids is None:
            series_ids = list(DEFAULT_SERIES.keys())
        
        indicators = []
        
        for series_id in series_ids:
            try:
                latest = self.get_latest(series_id)
                if latest:
                    indicators.append(latest)
            except Exception as e:
                logger.warning(f"Failed to fetch {series_id}: {e}")
        
        return indicators
    
    def get_series_history(
        self,
        series_id: str,
        days_back: int = 365,
    ) -> list[dict]:
        """
        Get historical data for a series.
        
        Args:
            series_id: FRED series ID
            days_back: Number of days of history
            
        Returns:
            List of observation dicts
        """
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        data = self.get_series(series_id, start_date=start_date, limit=1000)
        
        return [
            {
                "series_id": series_id,
                "name": data.get("title"),
                "value": float(obs["value"]) if obs["value"] != "." else None,
                "date": obs["date"],
                "units": data.get("units"),
            }
            for obs in data.get("observations", [])
            if obs["value"] != "."
        ]
    
    def _cache_path(self, key: str) -> Path:
        """Get path for a cache key."""
        safe_key = "".join(c if c.isalnum() else "_" for c in key)[:100]
        return CACHE_DIR / f"fred_{safe_key}.json"
    
    def _read_cache(self, key: str, ignore_ttl: bool = False) -> Optional[dict]:
        """Read data from cache if fresh."""
        path = self._cache_path(key)
        
        if not path.exists():
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            
            if not ignore_ttl:
                cached_at = datetime.fromisoformat(cached["cached_at"])
                age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                
                if age_hours > self.cache_ttl_hours:
                    return None
            
            return cached["data"]
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid cache file {path}: {e}")
            return None
    
    def _write_cache(self, key: str, data: dict) -> None:
        """Write data to cache."""
        path = self._cache_path(key)
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "cached_at": datetime.now().isoformat(),
                    "data": data
                }, f, indent=2)
        except IOError as e:
            logger.warning(f"Failed to write cache {path}: {e}")


def fetch_key_indicators() -> list[dict]:
    """Fetch current values for key economic indicators."""
    client = FREDClient()
    return client.get_all_indicators()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching key economic indicators from FRED...\n")
    indicators = fetch_key_indicators()
    
    for ind in indicators:
        print(f"{ind['name']}")
        print(f"  {ind['series_id']}: {ind['value']} ({ind['date']})")
        print()
