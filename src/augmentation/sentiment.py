"""Sentiment analysis for social media posts using VADER."""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def score_sentiment(text: str) -> dict:
    """Score sentiment of text using VADER lexicon.

    Args:
        text: Input text to analyse.

    Returns:
        dict with keys: compound (-1 to 1), pos, neu, neg (0 to 1),
        and label ('positive', 'negative', or 'neutral').
    """
    if not text or not text.strip():
        return {
            "compound": 0.0,
            "pos": 0.0,
            "neu": 1.0,
            "neg": 0.0,
            "label": "neutral",
        }

    scores = _analyzer.polarity_scores(text)

    if scores["compound"] >= 0.05:
        label = "positive"
    elif scores["compound"] <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "compound": scores["compound"],
        "pos": scores["pos"],
        "neu": scores["neu"],
        "neg": scores["neg"],
        "label": label,
    }
