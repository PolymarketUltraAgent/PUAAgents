import os
import anthropic
from google import genai
from google.genai import types as genai_types
from dataclasses import dataclass
from dotenv import load_dotenv

from market_fetcher import MarketSnapshot
from news_aggregator import NewsArticle

load_dotenv()

ANTHROPIC_MODEL = "claude-sonnet-4-6"
GEMINI_MODEL = "gemini-2.0-flash"
EDGE_THRESHOLD = 0.05

SYSTEM_PROMPT = """\
You are a well-calibrated prediction market analyst. Your job is to estimate the \
true probability of a market resolving YES based on recent news.

Be objective. Do not anchor to the current market price. Base your estimate purely \
on the evidence in the news and your knowledge of base rates. If news is sparse or \
contradictory, reflect that with a lower confidence score."""

TOOL_SCHEMA = {
    "name": "estimate_probability",
    "description": "Estimate the fair probability of a prediction market resolving YES.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fair_prob": {
                "type": "number",
                "description": "Estimated true probability the market resolves YES (0.0–1.0).",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this estimate (0.0–1.0). Lower when news is sparse.",
            },
            "rationale": {
                "type": "string",
                "description": "Concise explanation citing specific news.",
            },
        },
        "required": ["fair_prob", "confidence", "rationale"],
    },
}


@dataclass
class AlphaSignal:
    market_id: str
    question: str
    implied_prob: float
    fair_prob: float
    edge: float
    confidence: float
    rationale: str
    is_signal: bool
    provider: str           # "anthropic" | "gemini"


def _get_provider() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    raise EnvironmentError(
        "No LLM API key found. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env"
    )


def _build_user_prompt(snapshot: MarketSnapshot, articles: list[NewsArticle]) -> str:
    news_block = "\n\n".join(
        f"{i+1}. {a.title} ({a.published_date})\n   {a.content}"
        for i, a in enumerate(articles)
    ) if articles else "No recent news found."

    return (
        f"Market question: {snapshot.question}\n"
        f"Current market implied probability: {snapshot.yes_price:.0%} YES\n\n"
        f"Recent news:\n{news_block}\n\n"
        f"Estimate the true probability this market resolves YES."
    )


def _call_anthropic(user_prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input


def _call_gemini(user_prompt: str) -> dict:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    estimate_fn = genai_types.FunctionDeclaration(
        name=TOOL_SCHEMA["name"],
        description=TOOL_SCHEMA["description"],
        parameters=genai_types.Schema(
            type=genai_types.Type.OBJECT,
            properties={
                "fair_prob": genai_types.Schema(type=genai_types.Type.NUMBER),
                "confidence": genai_types.Schema(type=genai_types.Type.NUMBER),
                "rationale": genai_types.Schema(type=genai_types.Type.STRING),
            },
            required=["fair_prob", "confidence", "rationale"],
        ),
    )

    config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[genai_types.Tool(function_declarations=[estimate_fn])],
        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(mode="ANY")
        ),
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_prompt,
        config=config,
    )

    fc = response.candidates[0].content.parts[0].function_call
    return {k: v for k, v in fc.args.items()}


def analyze(snapshot: MarketSnapshot, articles: list[NewsArticle]) -> AlphaSignal:
    """Run the AlphaEngine: estimate fair probability and compute edge."""
    provider = _get_provider()
    user_prompt = _build_user_prompt(snapshot, articles)

    if provider == "anthropic":
        result = _call_anthropic(user_prompt)
    else:
        result = _call_gemini(user_prompt)

    fair_prob = float(result["fair_prob"])
    confidence = float(result["confidence"])
    edge = round(abs(fair_prob - snapshot.yes_price), 4)

    return AlphaSignal(
        market_id=snapshot.market_id,
        question=snapshot.question,
        implied_prob=snapshot.yes_price,
        fair_prob=round(fair_prob, 4),
        edge=edge,
        confidence=round(confidence, 4),
        rationale=result["rationale"],
        is_signal=edge >= EDGE_THRESHOLD,
        provider=provider,
    )
