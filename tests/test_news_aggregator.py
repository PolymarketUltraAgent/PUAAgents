import pytest
from unittest.mock import patch, MagicMock
from news_aggregator import NewsArticle, fetch_news


MOCK_RESPONSE = {
    "results": [
        {
            "title": "Oil prices surge amid OPEC cuts",
            "url": "https://example.com/oil-1",
            "content": "Oil prices rose sharply after OPEC announced further production cuts...",
            "score": 0.92,
            "published_date": "2025-05-10",
        },
        {
            "title": "Brent crude approaches $95 per barrel",
            "url": "https://example.com/oil-2",
            "content": "Brent crude oil continued its upward trend, nearing $95...",
            "score": 0.87,
            "published_date": "2025-05-09",
        },
    ]
}


def mock_post(*args, **kwargs):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    return mock_resp


# --- fetch_news ---

def test_fetch_news_returns_articles():
    with patch("news_aggregator.aggregator.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post = mock_post
        articles = fetch_news("Will oil price exceed $100?")

    assert len(articles) == 2
    assert all(isinstance(a, NewsArticle) for a in articles)


def test_fetch_news_article_fields():
    with patch("news_aggregator.aggregator.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post = mock_post
        articles = fetch_news("Will oil price exceed $100?")

    first = articles[0]
    assert first.title == "Oil prices surge amid OPEC cuts"
    assert first.url == "https://example.com/oil-1"
    assert first.score == pytest.approx(0.92)
    assert first.published_date == "2025-05-10"
    assert "OPEC" in first.content


def test_fetch_news_empty_results():
    with patch("news_aggregator.aggregator.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post = MagicMock(
            return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"results": []}),
            )
        )
        articles = fetch_news("obscure query with no results")

    assert articles == []


def test_fetch_news_missing_api_key_raises():
    with patch.dict("os.environ", {}, clear=True), \
         patch("news_aggregator.aggregator.load_dotenv"):
        with pytest.raises(EnvironmentError, match="TAVILY_API_KEY"):
            fetch_news("some query")


def test_fetch_news_passes_correct_params():
    captured = {}

    def capture_post(url, json=None, **kwargs):
        captured.update(json or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        return mock_resp

    with patch("news_aggregator.aggregator.httpx.Client") as mock_client, \
         patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
        mock_client.return_value.__enter__.return_value.post = capture_post
        fetch_news("test query", max_results=3, days=14)

    assert captured["query"] == "test query"
    assert captured["max_results"] == 3
    assert captured["days"] == 14
    assert captured["api_key"] == "test-key"
