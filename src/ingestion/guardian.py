"""
Guardian API Client

Fetches news articles from The Guardian's Open Platform API.
Docs: https://open-platform.theguardian.com/documentation/

Supports both live fetching and cached data for reliable demos.
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

# Guardian API endpoint
BASE_URL = "https://content.guardianapis.com"

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


class GuardianClient:
    """Client for fetching news articles from The Guardian."""
    
    def __init__(self, api_key: str = None, use_cache: bool = True, cache_ttl_hours: int = 1):
        """
        Args:
            api_key: Guardian API key (defaults to GUARDIAN_API_KEY env var)
            use_cache: If True, return cached data when available
            cache_ttl_hours: How long cached data is considered fresh
        """
        self.api_key = api_key or os.getenv("GUARDIAN_API_KEY")
        if not self.api_key:
            raise ValueError("Guardian API key required. Set GUARDIAN_API_KEY in .env")
        
        self.use_cache = use_cache
        self.cache_ttl_hours = cache_ttl_hours
        self.session = requests.Session()
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def search(
        self,
        query: str,
        section: str = None,
        from_date: str = None,
        to_date: str = None,
        page_size: int = 50,
        page: int = 1,
        order_by: str = "newest",
        show_fields: str = "headline,standfirst,body,byline",
    ) -> dict:
        """
        Search for articles.
        
        Args:
            query: Search term (e.g., "Iran", "Trump tariffs", "prediction markets")
            section: Filter by section (e.g., "world", "politics", "business")
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            page_size: Results per page (max 200)
            page: Page number
            order_by: Sort order (newest, oldest, relevance)
            show_fields: Fields to include in response
            
        Returns:
            API response with results
        """
        cache_key = f"search_{query}_{section}_{from_date}_{page_size}_{page}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached Guardian search for '{query}'")
                return cached
        
        try:
            params = {
                "api-key": self.api_key,
                "q": query,
                "page-size": page_size,
                "page": page,
                "order-by": order_by,
                "show-fields": show_fields,
            }
            
            if section:
                params["section"] = section
            if from_date:
                params["from-date"] = from_date
            if to_date:
                params["to-date"] = to_date
            
            response = self.session.get(f"{BASE_URL}/search", params=params)
            response.raise_for_status()
            
            data = response.json()
            
            self._write_cache(cache_key, data)
            
            results_count = len(data.get("response", {}).get("results", []))
            logger.info(f"Fetched {results_count} articles from Guardian for '{query}'")
            
            return data
            
        except requests.RequestException as e:
            logger.error(f"Failed to search Guardian for '{query}': {e}")
            
            cached = self._read_cache(cache_key, ignore_ttl=True)
            if cached:
                logger.warning("Using expired cache as fallback")
                return cached
            
            raise
    
    def search_articles(
        self,
        query: str,
        days_back: int = 7,
        max_results: int = 50,
        section: str = None,
    ) -> list[dict]:
        """
        Convenience method: search and return normalized article list.
        
        Args:
            query: Search term
            days_back: How many days back to search
            max_results: Maximum articles to return
            section: Optional section filter
            
        Returns:
            List of normalized article dictionaries
        """
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        response = self.search(
            query=query,
            from_date=from_date,
            page_size=min(max_results, 200),
            section=section,
        )
        
        results = response.get("response", {}).get("results", [])
        
        # Normalize to consistent format
        articles = []
        for r in results[:max_results]:
            fields = r.get("fields", {})
            articles.append({
                "id": r.get("id"),
                "title": fields.get("headline") or r.get("webTitle"),
                "content": fields.get("body"),
                "summary": fields.get("standfirst"),
                "url": r.get("webUrl"),
                "published_at": r.get("webPublicationDate"),
                "author": fields.get("byline"),
                "section": r.get("sectionName"),
                "source": "guardian",
                "raw_data": r,
            })
        
        return articles
    
    def get_sections(self) -> list[dict]:
        """Get list of available sections."""
        try:
            params = {"api-key": self.api_key}
            response = self.session.get(f"{BASE_URL}/sections", params=params)
            response.raise_for_status()
            
            return response.json().get("response", {}).get("results", [])
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch sections: {e}")
            return []
    
    def _cache_path(self, key: str) -> Path:
        """Get path for a cache key."""
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return CACHE_DIR / f"guardian_{safe_key}.json"
    
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


# Convenience function for quick testing
def fetch_recent_news(query: str, days: int = 7, limit: int = 10) -> list[dict]:
    """Fetch recent news articles matching query."""
    client = GuardianClient()
    articles = client.search_articles(query, days_back=days, max_results=limit)
    
    return [
        {
            "title": a["title"],
            "published": a["published_at"][:10] if a["published_at"] else None,
            "section": a["section"],
            "url": a["url"],
        }
        for a in articles
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching recent Iran news from The Guardian...")
    articles = fetch_recent_news("Iran", days=7, limit=5)
    
    for a in articles:
        print(f"\n{a['title']}")
        print(f"  {a['published']} | {a['section']}")
        print(f"  {a['url']}")
