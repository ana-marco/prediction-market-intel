"""
gov.uk Web Scraper

Scrapes press releases and policy announcements from gov.uk.
Fulfills the web scraping requirement for the assignment.

Target: https://www.gov.uk/search/news-and-communications
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = "https://www.gov.uk"
SEARCH_URL = "https://www.gov.uk/search/news-and-communications"

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


class GovUKScraper:
    """Scraper for gov.uk press releases and announcements."""
    
    def __init__(self, use_cache: bool = True, cache_ttl_hours: int = 6):
        """
        Args:
            use_cache: If True, return cached data when available
            cache_ttl_hours: How long cached data is considered fresh
        """
        self.use_cache = use_cache
        self.cache_ttl_hours = cache_ttl_hours
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "UCL-MSIN0166-DataEngineering/1.0 (Academic Research Project)"
        })
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def search(
        self,
        keywords: str = None,
        topic: str = None,
        organisation: str = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        """
        Search gov.uk news and communications.
        
        Args:
            keywords: Search terms
            topic: Filter by topic (e.g., "foreign-affairs", "defence-and-armed-forces")
            organisation: Filter by department (e.g., "foreign-commonwealth-development-office")
            page: Page number
            per_page: Results per page (max seems to be ~40)
            
        Returns:
            List of article dictionaries
        """
        cache_key = f"govuk_search_{keywords}_{topic}_{page}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                logger.info(f"Using cached gov.uk search for '{keywords}'")
                return cached
        
        # Build query params
        params = {
            "content_store_document_type": "news_story,press_release,government_response",
            "order": "updated-newest",
            "page": page,
        }
        
        if keywords:
            params["keywords"] = keywords
        if topic:
            params["topic"] = topic
        if organisation:
            params["organisations[]"] = organisation
        
        try:
            url = f"{SEARCH_URL}?{urlencode(params, doseq=True)}"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            articles = self._parse_search_results(response.text)
            
            self._write_cache(cache_key, articles)
            
            logger.info(f"Scraped {len(articles)} articles from gov.uk for '{keywords}'")
            return articles
            
        except requests.RequestException as e:
            logger.error(f"Failed to scrape gov.uk: {e}")
            
            cached = self._read_cache(cache_key, ignore_ttl=True)
            if cached:
                logger.warning("Using expired cache as fallback")
                return cached
            
            raise
    
    def _parse_search_results(self, html: str) -> list[dict]:
        """Parse search results page."""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        
        # Find all result items
        results = soup.select("li.gem-c-document-list__item")
        
        for item in results:
            try:
                # Title and URL
                title_div = item.select_one(".gem-c-document-list__item-title")
                if not title_div:
                    continue
                
                link = title_div.select_one("a")
                if not link:
                    continue
                
                title = link.get_text(strip=True)
                url = urljoin(BASE_URL, link.get("href", ""))
                
                # Description
                desc_elem = item.select_one(".gem-c-document-list__item-description")
                description = desc_elem.get_text(strip=True) if desc_elem else None
                
                # Date from time element
                time_elem = item.select_one("time")
                published_at = time_elem.get("datetime") if time_elem else None
                
                # gov.uk HTML doesn't expose document type reliably,
                # so we default to "news" for all press releases
                doc_type = "news"
                
                articles.append({
                    "title": title,
                    "url": url,
                    "summary": description,
                    "published_at": published_at,
                    "document_type": doc_type,
                    "source": "govuk",
                })
                
            except Exception as e:
                logger.warning(f"Failed to parse result item: {e}")
                continue
        
        return articles
    
    def get_article_content(self, url: str) -> Optional[dict]:
        """
        Fetch full content of a single article.
        
        Args:
            url: Article URL
            
        Returns:
            Article dict with full content
        """
        cache_key = f"govuk_article_{hash(url)}"
        
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached:
                return cached
        
        try:
            # Be polite - don't hammer the server
            time.sleep(0.5)
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Title
            title_elem = soup.select_one("h1")
            title = title_elem.get_text(strip=True) if title_elem else None
            
            # Main content
            content_elem = soup.select_one(".govspeak") or soup.select_one("article")
            content = content_elem.get_text(separator="\n", strip=True) if content_elem else None
            
            # Published date
            time_elem = soup.select_one("time")
            published_at = time_elem.get("datetime") if time_elem else None
            
            # Organisation
            org_elem = soup.select_one(".gem-c-organisation-logo__name")
            organisation = org_elem.get_text(strip=True) if org_elem else None
            
            article = {
                "title": title,
                "url": url,
                "content": content,
                "published_at": published_at,
                "organisation": organisation,
                "source": "govuk",
            }
            
            self._write_cache(cache_key, article)
            
            return article
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch article {url}: {e}")
            return None
    
    def search_articles(
        self,
        keywords: str,
        max_results: int = 20,
        fetch_content: bool = False,
    ) -> list[dict]:
        """
        Convenience method: search and optionally fetch full content.
        
        Args:
            keywords: Search terms
            max_results: Maximum articles to return
            fetch_content: If True, fetch full article content (slower)
            
        Returns:
            List of article dictionaries
        """
        articles = self.search(keywords=keywords)[:max_results]
        
        if fetch_content:
            for i, article in enumerate(articles):
                logger.info(f"Fetching content {i+1}/{len(articles)}: {article['title'][:50]}...")
                full = self.get_article_content(article["url"])
                if full and full.get("content"):
                    article["content"] = full["content"]
                    article["organisation"] = full.get("organisation")
        
        return articles
    
    def _cache_path(self, key: str) -> Path:
        """Get path for a cache key."""
        safe_key = "".join(c if c.isalnum() else "_" for c in key)[:100]
        return CACHE_DIR / f"govuk_{safe_key}.json"
    
    def _read_cache(self, key: str, ignore_ttl: bool = False) -> Optional[list | dict]:
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
    
    def _write_cache(self, key: str, data: list | dict) -> None:
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


def fetch_recent_announcements(keywords: str = None, limit: int = 10) -> list[dict]:
    """Fetch recent government announcements."""
    scraper = GovUKScraper()
    articles = scraper.search(keywords=keywords)[:limit]
    
    return [
        {
            "title": a["title"],
            "published": a.get("published_at", "")[:10] if a.get("published_at") else None,
            "type": a.get("document_type"),
            "url": a["url"],
        }
        for a in articles
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching recent gov.uk announcements about foreign policy...")
    articles = fetch_recent_announcements("foreign policy", limit=5)
    
    for a in articles:
        print(f"\n{a['title']}")
        print(f"  {a['published']} | {a['type']}")
        print(f"  {a['url']}")
