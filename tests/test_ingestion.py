"""
Tests for data ingestion clients.

Covers: PolymarketClient, GuardianClient, GovUKScraper, FREDClient,
RedditClient, and the shared extract_topics_from_markets() utility.

All HTTP calls are mocked -- these tests run without network or Docker.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.utils.topic_extraction import (
    extract_topics_from_markets,
    _FALLBACK_TOPICS,
)


# ── Polymarket ──────────────────────────────────────────────────────


class TestPolymarket:

    def _make_client(self, tmp_path, monkeypatch):
        """Create a PolymarketClient with cache redirected to tmp_path."""
        monkeypatch.setattr("src.ingestion.polymarket.CACHE_DIR", tmp_path)
        from src.ingestion.polymarket import PolymarketClient
        return PolymarketClient(use_cache=True, cache_ttl_hours=1)

    def test_get_markets_parses_response(self, tmp_path, monkeypatch):
        """API returns a JSON list and the client passes it through."""
        client = self._make_client(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"id": "1", "question": "Will X happen?", "volume24hr": 100},
            {"id": "2", "question": "Will Y happen?", "volume24hr": 200},
        ]
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        markets = client.get_markets(limit=2)

        assert len(markets) == 2
        assert markets[0]["question"] == "Will X happen?"
        client.session.get.assert_called_once()

    def test_get_markets_writes_and_reads_cache(self, tmp_path, monkeypatch):
        """Second call returns cached data without hitting the API."""
        client = self._make_client(tmp_path, monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "1"}]
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        # First call: hits API and writes cache
        client.get_markets(limit=5)
        assert client.session.get.call_count == 1

        # Second call: should use cache, not API
        result = client.get_markets(limit=5)
        assert client.session.get.call_count == 1  # still 1
        assert result == [{"id": "1"}]

    def test_cache_ttl_expires(self, tmp_path, monkeypatch):
        """Stale cache is ignored and a fresh API call is made."""
        client = self._make_client(tmp_path, monkeypatch)

        # Pre-write an expired cache file
        cache_path = client._cache_path("markets_5_True_False_volume24hr")
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        cache_path.write_text(json.dumps({"cached_at": old_time, "data": [{"id": "old"}]}))

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "fresh"}]
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_markets(limit=5)
        assert result == [{"id": "fresh"}]
        client.session.get.assert_called_once()

    def test_api_failure_falls_back_to_expired_cache(self, tmp_path, monkeypatch):
        """When API fails, expired cache is returned as fallback."""
        client = self._make_client(tmp_path, monkeypatch)

        # Pre-write expired cache
        cache_path = client._cache_path("markets_100_True_False_volume24hr")
        old_time = (datetime.now() - timedelta(hours=5)).isoformat()
        cache_path.write_text(json.dumps({"cached_at": old_time, "data": [{"id": "stale"}]}))

        client.session.get = MagicMock(side_effect=requests.RequestException("timeout"))

        result = client.get_markets()
        assert result == [{"id": "stale"}]

    def test_fetch_top_markets_extracts_fields(self, tmp_path, monkeypatch):
        """fetch_top_markets() normalises camelCase API keys."""
        monkeypatch.setattr("src.ingestion.polymarket.CACHE_DIR", tmp_path)
        from src.ingestion.polymarket import PolymarketClient, fetch_top_markets

        raw = [
            {
                "id": "abc",
                "question": "Will it rain?",
                "outcomePrices": "[0.6, 0.4]",
                "volume24hr": 5000,
                "liquidity": 12000,
                "endDate": "2025-06-01",
            }
        ]
        with patch.object(PolymarketClient, "get_markets", return_value=raw):
            result = fetch_top_markets(n=1)

        assert len(result) == 1
        assert result[0]["question"] == "Will it rain?"
        assert result[0]["outcome_prices"] == "[0.6, 0.4]"
        assert result[0]["volume_24h"] == 5000


# ── Guardian ────────────────────────────────────────────────────────


class TestGuardian:

    def test_missing_api_key_raises(self, monkeypatch):
        """Instantiation without API key raises ValueError."""
        from src.ingestion.guardian import GuardianClient
        monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)

        with pytest.raises(ValueError, match="Guardian API key required"):
            GuardianClient(api_key=None)

    def _make_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ingestion.guardian.CACHE_DIR", tmp_path)
        monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
        from src.ingestion.guardian import GuardianClient
        return GuardianClient()

    def test_search_articles_normalizes_fields(self, tmp_path, monkeypatch):
        """Nested Guardian fields are flattened into a clean dict."""
        client = self._make_client(tmp_path, monkeypatch)
        api_response = {
            "response": {
                "results": [
                    {
                        "id": "world/2025/iran",
                        "webTitle": "Fallback Title",
                        "webUrl": "https://theguardian.com/article",
                        "webPublicationDate": "2025-03-01T12:00:00Z",
                        "sectionName": "World news",
                        "fields": {
                            "headline": "Iran headline",
                            "body": "<p>Article body</p>",
                            "standfirst": "Summary text",
                            "byline": "John Doe",
                        },
                    }
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        articles = client.search_articles("Iran", days_back=7)

        assert len(articles) == 1
        a = articles[0]
        assert a["title"] == "Iran headline"
        assert a["content"] == "<p>Article body</p>"
        assert a["summary"] == "Summary text"
        assert a["author"] == "John Doe"
        assert a["source"] == "guardian"

    def test_search_articles_falls_back_to_webTitle(self, tmp_path, monkeypatch):
        """When fields.headline is missing, webTitle is used."""
        client = self._make_client(tmp_path, monkeypatch)
        api_response = {
            "response": {
                "results": [
                    {
                        "id": "a/1",
                        "webTitle": "Web Title Here",
                        "webUrl": "https://theguardian.com/a",
                        "webPublicationDate": "2025-03-01T12:00:00Z",
                        "sectionName": "World",
                        "fields": {},  # no headline
                    }
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        articles = client.search_articles("test")
        assert articles[0]["title"] == "Web Title Here"

    def test_search_returns_raw_response(self, tmp_path, monkeypatch):
        """search() returns the full API response as-is."""
        client = self._make_client(tmp_path, monkeypatch)
        raw = {"response": {"status": "ok", "results": []}}
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.search("Iran")
        assert result == raw

    def test_api_failure_uses_expired_cache(self, tmp_path, monkeypatch):
        """When API fails, expired cache is returned."""
        client = self._make_client(tmp_path, monkeypatch)

        cache_path = client._cache_path("search_Iran_None_None_50_1")
        old_time = (datetime.now() - timedelta(hours=5)).isoformat()
        cache_data = {"response": {"results": [{"id": "cached"}]}}
        cache_path.write_text(json.dumps({"cached_at": old_time, "data": cache_data}))

        client.session.get = MagicMock(side_effect=requests.RequestException("fail"))

        result = client.search("Iran")
        assert result == cache_data


# ── gov.uk ──────────────────────────────────────────────────────────


class TestGovUK:

    SEARCH_HTML = """
    <ul>
      <li class="gem-c-document-list__item">
        <div class="gem-c-document-list__item-title">
          <a href="/government/news/trade-deal">Trade deal announced</a>
        </div>
        <p class="gem-c-document-list__item-description">Summary of trade deal</p>
        <time datetime="2025-03-15">15 March 2025</time>
      </li>
      <li class="gem-c-document-list__item">
        <div class="gem-c-document-list__item-title">
          <!-- missing <a> tag - malformed -->
        </div>
      </li>
    </ul>
    """

    ARTICLE_HTML = """
    <html>
      <h1>Full Article Title</h1>
      <time datetime="2025-03-15T10:00:00Z">15 March 2025</time>
      <div class="govspeak"><p>Paragraph one.</p><p>Paragraph two.</p></div>
      <span class="gem-c-organisation-logo__name">FCDO</span>
    </html>
    """

    def _make_scraper(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ingestion.govuk_scraper.CACHE_DIR", tmp_path)
        from src.ingestion.govuk_scraper import GovUKScraper
        return GovUKScraper()

    def test_parse_search_results_extracts_articles(self, tmp_path, monkeypatch):
        """HTML is parsed into structured article dicts."""
        scraper = self._make_scraper(tmp_path, monkeypatch)
        results = scraper._parse_search_results(self.SEARCH_HTML)

        # Only 1 valid result (second item has no <a>)
        assert len(results) == 1
        article = results[0]
        assert article["title"] == "Trade deal announced"
        assert article["url"].endswith("/government/news/trade-deal")
        assert article["summary"] == "Summary of trade deal"
        assert article["published_at"] == "2025-03-15"
        assert article["source"] == "govuk"

    def test_parse_search_results_skips_malformed(self, tmp_path, monkeypatch):
        """Items without an <a> tag in the title div are skipped."""
        scraper = self._make_scraper(tmp_path, monkeypatch)
        bad_html = """
        <ul>
          <li class="gem-c-document-list__item">
            <div class="gem-c-document-list__item-title">No link here</div>
          </li>
        </ul>
        """
        results = scraper._parse_search_results(bad_html)
        assert len(results) == 0

    def test_get_article_content_parses_html(self, tmp_path, monkeypatch):
        """Full article page is parsed for title, content, date, org."""
        scraper = self._make_scraper(tmp_path, monkeypatch)
        monkeypatch.setattr("src.ingestion.govuk_scraper.time.sleep", lambda _: None)

        mock_resp = MagicMock()
        mock_resp.text = self.ARTICLE_HTML
        mock_resp.raise_for_status = MagicMock()
        scraper.session.get = MagicMock(return_value=mock_resp)

        article = scraper.get_article_content("https://www.gov.uk/test")

        assert article["title"] == "Full Article Title"
        assert "Paragraph one" in article["content"]
        assert article["published_at"] == "2025-03-15T10:00:00Z"
        assert article["organisation"] == "FCDO"

    def test_cache_key_truncation(self, tmp_path, monkeypatch):
        """Cache filenames are truncated to avoid OS path limits."""
        scraper = self._make_scraper(tmp_path, monkeypatch)
        long_key = "a" * 200
        path = scraper._cache_path(long_key)
        # Filename should be govuk_ + (100 chars max) + .json
        stem = path.stem  # e.g. govuk_aaaa...
        assert len(stem) <= 100 + len("govuk_")


# ── FRED ────────────────────────────────────────────────────────────


class TestFRED:

    def test_missing_api_key_raises(self, monkeypatch):
        """Instantiation without API key raises ValueError."""
        from src.ingestion.fred import FREDClient
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        with pytest.raises(ValueError, match="FRED API key required"):
            FREDClient(api_key=None)

    def _make_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ingestion.fred.CACHE_DIR", tmp_path)
        monkeypatch.setenv("FRED_API_KEY", "test-key")
        from src.ingestion.fred import FREDClient
        return FREDClient()

    def _mock_series_response(self, client):
        """Set up mock for the two-API-call pattern in get_series()."""
        info_resp = MagicMock()
        info_resp.json.return_value = {
            "seriess": [{"id": "FEDFUNDS", "title": "Fed Rate", "units": "Percent", "frequency": "Monthly"}]
        }
        info_resp.raise_for_status = MagicMock()

        obs_resp = MagicMock()
        obs_resp.json.return_value = {
            "observations": [
                {"date": "2025-01-01", "value": "5.33"},
                {"date": "2024-12-01", "value": "5.25"},
                {"date": "2024-11-01", "value": "."},
            ]
        }
        obs_resp.raise_for_status = MagicMock()

        client.session.get = MagicMock(side_effect=[info_resp, obs_resp])

    def test_get_series_makes_two_api_calls(self, tmp_path, monkeypatch):
        """get_series() calls /series (metadata) and /series/observations."""
        client = self._make_client(tmp_path, monkeypatch)
        self._mock_series_response(client)

        result = client.get_series("FEDFUNDS")

        assert client.session.get.call_count == 2
        assert result["series_id"] == "FEDFUNDS"
        assert result["title"] == "Fed Rate"
        assert len(result["observations"]) == 3

    def test_get_latest_returns_float_value(self, tmp_path, monkeypatch):
        """Numeric string observation is converted to float."""
        client = self._make_client(tmp_path, monkeypatch)

        info_resp = MagicMock()
        info_resp.json.return_value = {"seriess": [{"title": "Fed Rate", "units": "Percent", "frequency": "Monthly"}]}
        info_resp.raise_for_status = MagicMock()

        obs_resp = MagicMock()
        obs_resp.json.return_value = {"observations": [{"date": "2025-01-01", "value": "5.33"}]}
        obs_resp.raise_for_status = MagicMock()

        client.session.get = MagicMock(side_effect=[info_resp, obs_resp])

        result = client.get_latest("FEDFUNDS")
        assert result["value"] == 5.33
        assert isinstance(result["value"], float)

    def test_get_latest_handles_missing_value(self, tmp_path, monkeypatch):
        """FRED's missing value marker '.' is converted to None."""
        client = self._make_client(tmp_path, monkeypatch)

        info_resp = MagicMock()
        info_resp.json.return_value = {"seriess": [{"title": "VIX", "units": "Index", "frequency": "Daily"}]}
        info_resp.raise_for_status = MagicMock()

        obs_resp = MagicMock()
        obs_resp.json.return_value = {"observations": [{"date": "2025-01-01", "value": "."}]}
        obs_resp.raise_for_status = MagicMock()

        client.session.get = MagicMock(side_effect=[info_resp, obs_resp])

        result = client.get_latest("VIXCLS")
        assert result["value"] is None

    def test_get_series_history_filters_missing(self, tmp_path, monkeypatch):
        """Observations with value '.' are excluded from history."""
        client = self._make_client(tmp_path, monkeypatch)
        self._mock_series_response(client)

        history = client.get_series_history("FEDFUNDS", days_back=365)

        # 3 observations in mock, 1 has "." -> only 2 returned
        assert len(history) == 2
        assert all(h["value"] is not None for h in history)


# ── Reddit ──────────────────────────────────────────────────────────


class TestReddit:

    REDDIT_RESPONSE = {
        "data": {
            "children": [
                {"data": {"id": "a1", "title": "Normal post", "author": "user1",
                          "score": 42, "stickied": False, "selftext": "body",
                          "upvote_ratio": 0.95, "num_comments": 10,
                          "created_utc": 1700000000, "url": "https://example.com",
                          "permalink": "/r/test/comments/a1/normal/",
                          "is_self": True, "link_flair_text": None}},
                {"data": {"id": "a2", "title": "Stickied post", "author": "mod",
                          "score": 100, "stickied": True, "selftext": "rules",
                          "upvote_ratio": 0.99, "num_comments": 5,
                          "created_utc": 1700000000, "url": "https://example.com",
                          "permalink": "/r/test/comments/a2/stickied/",
                          "is_self": True, "link_flair_text": None}},
                {"data": {"id": "a3", "title": "Another post", "author": "user2",
                          "score": 15, "stickied": False, "selftext": "",
                          "upvote_ratio": 0.80, "num_comments": 3,
                          "created_utc": 1700000000, "url": "https://example.com",
                          "permalink": "/r/test/comments/a3/another/",
                          "is_self": True, "link_flair_text": "Discussion"}},
            ],
            "after": None,
        }
    }

    def _make_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ingestion.reddit.CACHE_DIR", tmp_path)
        monkeypatch.setattr("src.ingestion.reddit.time.sleep", lambda _: None)
        monkeypatch.setattr("src.ingestion.reddit.time.time", lambda: 999999)
        from src.ingestion.reddit import RedditClient
        return RedditClient(use_cache=False)

    def test_parse_posts_normalizes_fields(self, tmp_path, monkeypatch):
        """Reddit JSON structure is flattened into clean post dicts."""
        client = self._make_client(tmp_path, monkeypatch)
        posts = client._parse_posts(self.REDDIT_RESPONSE, "test")

        # 3 children minus 1 stickied = 2
        non_stickied = [p for p in posts if p["title"] != "Stickied post"]
        assert len(non_stickied) == 2

        post = non_stickied[0]
        assert post["post_id"] == "a1"
        assert post["subreddit"] == "test"
        assert post["permalink"] == "https://reddit.com/r/test/comments/a1/normal/"
        assert "fetched_at" in post

    def test_parse_posts_filters_stickied(self, tmp_path, monkeypatch):
        """Stickied posts are excluded from results."""
        client = self._make_client(tmp_path, monkeypatch)
        posts = client._parse_posts(self.REDDIT_RESPONSE, "test")
        assert len(posts) == 2
        assert all(p["title"] != "Stickied post" for p in posts)

    def test_search_posts_returns_empty_on_error(self, tmp_path, monkeypatch):
        """API failure returns [] instead of raising (unlike other clients)."""
        client = self._make_client(tmp_path, monkeypatch)
        client.session.get = MagicMock(side_effect=requests.RequestException("fail"))

        result = client.search_posts("test query")
        assert result == []

    def test_get_posts_from_subreddits_aggregates(self, tmp_path, monkeypatch):
        """Posts from multiple subreddits are combined into one list."""
        client = self._make_client(tmp_path, monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = self.REDDIT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_posts_from_subreddits(subreddits=["sub1", "sub2"])
        # 2 non-stickied posts per sub x 2 subs = 4
        assert len(result) == 4


# ── Topic Extraction ────────────────────────────────────────────────


class TestTopicExtraction:

    def _mock_db(self, markets):
        db = MagicMock()
        db.get_markets.return_value = markets
        return db

    def test_extracts_proper_nouns(self):
        """Capitalized phrases are extracted from market questions."""
        db = self._mock_db([
            {"question": "Will Iran attack Israel by 2025?"},
            {"question": "Will Trump win the election?"},
        ])
        topics = extract_topics_from_markets(db, source="guardian", max_topics=10)

        # Regex captures multi-word capitalized phrases like "Will Iran"
        # because both words start uppercase. Single-word proper nouns
        # like "Israel" are also captured.
        assert "Israel" in topics
        assert any("Iran" in t for t in topics)
        assert any("Trump" in t for t in topics)

    def test_guardian_extracts_quoted_terms(self):
        """Guardian source also picks up quoted terms from questions."""
        db = self._mock_db([
            {"question": 'Will "Elon Musk" buy Twitter?'},
        ])
        topics = extract_topics_from_markets(db, source="guardian", max_topics=10)
        assert "Elon Musk" in topics

    def test_govuk_maps_topics(self):
        """gov.uk source appends core UK policy topics."""
        db = self._mock_db([
            {"question": "China imposes tariffs on UK goods"},
            {"question": "China imposes tariffs on UK goods"},
        ])
        topics = extract_topics_from_markets(db, source="govuk", max_topics=10)

        # Core UK topics are always appended
        assert "foreign policy" in topics
        assert "defence" in topics
        assert "economy" in topics

    def test_reddit_filters_by_frequency(self):
        """Reddit source only keeps topics appearing in 2+ markets."""
        db = self._mock_db([
            {"question": "Iran is escalating tensions"},
            {"question": "Iran launches new sanctions response"},
            {"question": "Iran and Israel conflict deepens"},
            {"question": "Bitcoin hits new highs"},  # only 1 mention
        ])
        topics = extract_topics_from_markets(db, source="reddit", max_topics=10)

        # "Iran" appears 3 times (count >= 2), should be included
        assert any("Iran" in t for t in topics)
        # "Bitcoin" appears once (count < 2), should be excluded
        assert not any("Bitcoin" in t for t in topics)

    @pytest.mark.parametrize("source", ["guardian", "govuk", "reddit"])
    def test_fallback_when_no_markets(self, source):
        """Empty market list returns source-specific fallback topics."""
        db = self._mock_db([])
        topics = extract_topics_from_markets(db, source=source)
        assert topics == _FALLBACK_TOPICS[source]
