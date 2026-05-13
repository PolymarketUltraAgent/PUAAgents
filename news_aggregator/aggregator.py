import os
import httpx
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

TAVILY_URL = "https://api.tavily.com/search"


@dataclass
class NewsArticle:
    title: str
    url: str
    content: str        # snippet returned by Tavily
    score: float        # relevance score 0–1
    published_date: str # ISO date string, empty if unavailable


def _api_key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise EnvironmentError("TAVILY_API_KEY not set in environment")
    return key


def fetch_news(query: str, max_results: int = 5, days: int = 7) -> list[NewsArticle]:
    """Search for recent news articles relevant to a market question.

    Args:
        query: the market question or a derived search string
        max_results: number of articles to return
        days: only return articles published within this many days
    """
    payload = {
        "api_key": _api_key(),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "days": days,
        "include_answer": False,
    }

    with httpx.Client(timeout=15) as client:
        response = client.post(TAVILY_URL, json=payload)
        response.raise_for_status()

    results = response.json().get("results", [])
    return [
        NewsArticle(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            score=float(r.get("score", 0.0)),
            published_date=r.get("published_date", ""),
        )
        for r in results
    ]
