"""
Integration tests — hit the real Tavily API.
Run with: pytest tests/test_news_aggregator_integration.py -v -m integration
"""
import pytest
from news_aggregator import NewsArticle, fetch_news

pytestmark = pytest.mark.integration


def test_fetch_news_returns_results():
    articles = fetch_news("US presidential election odds 2024", max_results=3)

    assert isinstance(articles, list)
    assert len(articles) > 0
    assert all(isinstance(a, NewsArticle) for a in articles)


def test_fetch_news_articles_have_content():
    articles = fetch_news("oil price prediction market", max_results=3)

    for a in articles:
        assert a.title.strip() != ""
        assert a.url.startswith("http")
        assert a.content.strip() != ""
        assert 0.0 <= a.score <= 1.0


def test_fetch_news_respects_max_results():
    articles = fetch_news("inflation forecast", max_results=2)

    assert len(articles) <= 2


def test_fetch_news_recency_filter():
    articles = fetch_news("stock market news", max_results=5, days=3)

    assert isinstance(articles, list)
