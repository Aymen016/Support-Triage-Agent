from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from agent.schemas import KBArticleHit, KBSearchInput, KBSearchOutput, ToolError

KB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base" / "articles.json"

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "to", "of", "and", "or", "in",
    "on", "for", "my", "i", "it", "this", "that", "with", "have", "has", "do",
    "does", "did", "how", "what", "when", "why", "please", "hi", "hello", "thanks",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


@lru_cache(maxsize=1)
def _load_articles() -> list[dict]:
    with open(KB_PATH) as f:
        return json.load(f)


def search_knowledge_base(input: KBSearchInput) -> KBSearchOutput | ToolError:
    """
    Keyword-overlap search over the local KB (data/knowledge_base/articles.json).

    This is deliberately simple — a placeholder for the real embedding-based
    RAG retriever the project plan says to reuse from another project. Swap
    the scoring function below for a vector similarity lookup without
    touching the tool's input/output contract.
    """
    try:
        articles = _load_articles()
    except FileNotFoundError as e:
        return ToolError(tool="search_knowledge_base", error_type="not_found", message=str(e))

    query_tokens = _tokenize(input.query)
    if not query_tokens:
        return KBSearchOutput(hits=[])

    scored = []
    for article in articles:
        article_tokens = _tokenize(article["title"] + " " + article["content"])
        overlap = query_tokens & article_tokens
        if not overlap:
            continue
        score = len(overlap) / len(query_tokens)
        scored.append((score, article))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[: input.top_k]

    hits = [
        KBArticleHit(
            article_id=article["article_id"],
            title=article["title"],
            excerpt=article["content"][:180] + ("..." if len(article["content"]) > 180 else ""),
            score=round(min(score, 1.0), 3),
        )
        for score, article in top
    ]
    return KBSearchOutput(hits=hits)
