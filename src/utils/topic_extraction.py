"""
Shared topic extraction from Polymarket questions.

Used by load_guardian.py, load_govuk.py, and load_reddit.py to derive
search topics from whatever markets are already in PostgreSQL.
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Words that appear in market questions but aren't useful topics
_STOPWORDS = {
    "will", "the", "by", "in", "of", "to", "a", "an", "be", "is", "it",
    "for", "on", "at", "or", "and", "this", "that", "with", "as", "from",
    "before", "after", "during", "march", "april", "may", "june", "july",
    "2024", "2025", "2026", "2027", "2028", "yes", "no", "win", "lose",
    "happen", "end", "start", "over", "under", "more", "less", "than",
}

# Fallback topics when no markets are loaded, per source
_FALLBACK_TOPICS = {
    "guardian": [
        "US politics", "world news", "economy", "trade", "climate",
    ],
    "govuk": [
        "foreign policy", "defence", "trade", "economy", "energy",
    ],
    "reddit": [
        "federal reserve", "inflation", "oil prices", "bitcoin", "china",
    ],
}

# gov.uk maps US-centric market terms to UK-relevant search terms
_GOVUK_TOPIC_MAP = {
    "Iran": "Iran",
    "China": "China trade",
    "Trump": "US relations",
    "NATO": "NATO defence",
    "Oil": "energy policy",
    "Bitcoin": "cryptocurrency",
    "Fed": "interest rates",
    "Trade": "trade policy",
}

# gov.uk needs extra stopwords to filter US-specific noise
_GOVUK_EXTRA_STOPWORDS = {"cup", "world", "fifa", "election", "president"}


def extract_topics_from_markets(db, source: str, max_topics: int = 10) -> list[str]:
    """Extract search topics from loaded Polymarket questions.

    Args:
        db: PostgresClient instance with get_markets() method.
        source: One of "guardian", "govuk", "reddit".
        max_topics: Maximum number of topics to return.

    Returns:
        List of topic strings suitable for searching the given source.
    """
    markets = db.get_markets(limit=200)

    if not markets:
        logger.warning("No markets found. Using fallback topics.")
        return _FALLBACK_TOPICS.get(source, _FALLBACK_TOPICS["guardian"])

    stopwords = _STOPWORDS.copy()
    if source == "govuk":
        stopwords |= _GOVUK_EXTRA_STOPWORDS

    # Count capitalized words/phrases (proper nouns, topics)
    word_counts = Counter()
    for market in markets:
        question = market.get("question", "")
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
        for word in words:
            if word.lower() not in stopwords and len(word) > 2:
                word_counts[word] += 1

        # Guardian also extracts quoted terms
        if source == "guardian":
            for term in re.findall(r'"([^"]+)"', question):
                if term.lower() not in stopwords:
                    word_counts[term] += 1

    # Build topic list with source-specific logic
    if source == "govuk":
        topics = _build_govuk_topics(word_counts, max_topics)
    elif source == "reddit":
        topics = [
            w for w, c in word_counts.most_common(max_topics) if c >= 2
        ]
    else:
        topics = [w for w, _ in word_counts.most_common(max_topics)]

    logger.info(f"Extracted {len(topics)} topics from {len(markets)} markets")
    return topics


def _build_govuk_topics(word_counts: Counter, max_topics: int) -> list[str]:
    """Map market topics to UK-relevant search terms."""
    topics = []
    for word, count in word_counts.most_common(20):
        if word in _GOVUK_TOPIC_MAP:
            topics.append(_GOVUK_TOPIC_MAP[word])
        elif count >= 2:
            topics.append(word)
        if len(topics) >= max_topics:
            break

    core = ["foreign policy", "defence", "economy"]
    for t in core:
        if t not in topics and len(topics) < max_topics:
            topics.append(t)

    return topics
