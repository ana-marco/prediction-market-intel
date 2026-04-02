"""
Reddit Client

Fetches posts from Reddit using the public .json endpoint.
No authentication required - just append .json to any Reddit URL.

Target subreddits (curated for signal quality over volume):
- r/polymarket - prediction market discussions
- r/geopolitics - in-depth geopolitical analysis
- r/CredibleDefense - military/defense analysis, evidence-based
- r/NeutralPolitics - fact-based political discussion
- r/economics - economic analysis (Fed, inflation)
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"

# Subreddits relevant to prediction markets and geopolitical events
DEFAULT_SUBREDDITS = [
    "polymarket",        # Direct prediction market discussion
    "geopolitics",       # In-depth geopolitical analysis (732k members)
    "CredibleDefense",   # Military/defense analysis, evidence-based (118k)
    "NeutralPolitics",   # Fact-based political discussion, sourced claims
    "economics",         # Economic analysis (Fed, inflation, etc.)
]


class RedditClient:
    """Client for fetching Reddit posts via public JSON endpoint."""
    
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
            # Reddit requires a descriptive User-Agent
            "User-Agent": "UCL-MSIN0166-DataEngineering/1.0 (Academic Research Project)"
        })
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Rate limiting - Reddit allows ~60 requests/minute
        self.last_request = 0
        self.min_delay = 1.0  # seconds between requests
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request = time.time()
    
    def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        time_filter: str = "week",
        limit: int = 25,
        max_pages: int = 1,
    ) -> list[dict]:
        """
        Fetch posts from a subreddit.
        
        Args:
            subreddit: Subreddit name (without r/)
            sort: Sort order (hot, new, top, rising)
            time_filter: Time filter for top/controversial (hour, day, week, month, year, all)
            limit: Number of posts per page (max 100)
            max_pages: Number of pages to fetch (for more than 100 posts)
            
        Returns:
            List of post dictionaries
        """
        cache_key = f"reddit_{subreddit}_{sort}_{time_filter}_{limit}_{max_pages}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached Reddit data for r/{subreddit}")
                return cached
        
        all_posts = []
        after = None
        
        for page in range(max_pages):
            try:
                self._rate_limit()
                
                url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
                params = {"limit": min(limit, 100), "t": time_filter}
                if after:
                    params["after"] = after
                
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                posts = self._parse_posts(data, subreddit)
                all_posts.extend(posts)
                
                # Get next page token
                after = data.get("data", {}).get("after")
                if not after:
                    break  # No more pages
                    
            except requests.RequestException as e:
                logger.error(f"Failed to fetch r/{subreddit} page {page}: {e}")
                break
        
        self._write_cache(cache_key, all_posts)
        
        logger.info(f"Fetched {len(all_posts)} posts from r/{subreddit}")
        return all_posts
    
    def _parse_posts(self, data: dict, subreddit: str) -> list[dict]:
        """Parse Reddit API response into post list."""
        posts = []
        
        children = data.get("data", {}).get("children", [])
        
        for child in children:
            post_data = child.get("data", {})
            
            # Skip stickied/pinned posts
            if post_data.get("stickied"):
                continue
            
            posts.append({
                "post_id": post_data.get("id"),
                "subreddit": subreddit,
                "title": post_data.get("title"),
                "selftext": post_data.get("selftext", ""),
                "author": post_data.get("author"),
                "score": post_data.get("score", 0),
                "upvote_ratio": post_data.get("upvote_ratio", 0),
                "num_comments": post_data.get("num_comments", 0),
                "created_utc": post_data.get("created_utc"),
                "url": post_data.get("url"),
                "permalink": f"https://reddit.com{post_data.get('permalink', '')}",
                "is_self": post_data.get("is_self", False),
                "link_flair_text": post_data.get("link_flair_text"),
                "fetched_at": datetime.now().isoformat(),
            })
        
        return posts
    
    def search_posts(
        self,
        query: str,
        subreddit: str = None,
        sort: str = "relevance",
        time_filter: str = "week",
        limit: int = 25,
    ) -> list[dict]:
        """
        Search Reddit for posts matching a query.
        
        Args:
            query: Search terms
            subreddit: Limit to specific subreddit (optional)
            sort: Sort order (relevance, hot, top, new, comments)
            time_filter: Time filter (hour, day, week, month, year, all)
            limit: Number of results
            
        Returns:
            List of post dictionaries
        """
        cache_key = f"reddit_search_{query}_{subreddit}_{sort}_{time_filter}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached Reddit search for '{query}'")
                return cached
        
        try:
            self._rate_limit()
            
            if subreddit:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {"q": query, "restrict_sr": "on", "sort": sort, "t": time_filter, "limit": limit}
            else:
                url = "https://www.reddit.com/search.json"
                params = {"q": query, "sort": sort, "t": time_filter, "limit": limit}
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            posts = self._parse_posts(data, subreddit or "search")
            
            self._write_cache(cache_key, posts)
            
            logger.info(f"Found {len(posts)} posts for '{query}'")
            return posts
            
        except requests.RequestException as e:
            logger.error(f"Reddit search failed for '{query}': {e}")
            return []
    
    def get_posts_from_subreddits(
        self,
        subreddits: list[str] = None,
        sort: str = "hot",
        time_filter: str = "week",
        limit_per_sub: int = 25,
        max_pages: int = 1,
    ) -> list[dict]:
        """
        Fetch posts from multiple subreddits.
        
        Args:
            subreddits: List of subreddit names (defaults to DEFAULT_SUBREDDITS)
            sort: Sort order
            time_filter: Time filter
            limit_per_sub: Posts per page
            max_pages: Pages per subreddit
            
        Returns:
            Combined list of posts from all subreddits
        """
        if subreddits is None:
            subreddits = DEFAULT_SUBREDDITS
        
        all_posts = []
        
        for sub in subreddits:
            posts = self.get_subreddit_posts(
                subreddit=sub,
                sort=sort,
                time_filter=time_filter,
                limit=limit_per_sub,
                max_pages=max_pages,
            )
            all_posts.extend(posts)
        
        return all_posts
    
    def _cache_path(self, key: str) -> Path:
        """Get path for a cache key."""
        safe_key = "".join(c if c.isalnum() else "_" for c in key)[:100]
        return CACHE_DIR / f"reddit_{safe_key}.json"
    
    def _read_cache(self, key: str, ignore_ttl: bool = False) -> Optional[list]:
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
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Invalid cache file {path}: {e}")
            return None
    
    def _write_cache(self, key: str, data: list) -> None:
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


def fetch_trending_posts(limit: int = 10) -> list[dict]:
    """Fetch trending posts from default subreddits."""
    client = RedditClient()
    posts = client.get_posts_from_subreddits(limit_per_sub=limit)
    
    # Sort by score across all subreddits
    posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return posts[:limit * 2]  # Return top posts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching trending posts from financial subreddits...\n")
    posts = fetch_trending_posts(limit=5)
    
    for p in posts[:10]:
        print(f"r/{p['subreddit']} | {p['score']} pts")
        print(f"  {p['title'][:80]}")
        print()
