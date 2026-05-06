import asyncio
import logging
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

from config.settings import settings
from services.prompts import (
    SYSTEM_PROMPT,
    DIGEST_PROMPT_TEMPLATE,
    DEEP_DIVE_SYSTEM_PROMPT,
    DEEP_DIVE_SUMMARY_PROMPT,
    DEEP_DIVE_FOLLOWUP_SYSTEM,
    ARTICLE_SEARCH_SYSTEM,
    ARTICLE_SEARCH_PROMPT,
)
from services import news_fetcher

logger = logging.getLogger(__name__)

_GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_THINKING_CONFIG = {"thinkingLevel": "MINIMAL"}

# ---------------------------------------------------------------------------
# Workflow logger — logs/llm_workflow.log
# ---------------------------------------------------------------------------

_wf = logging.getLogger("llm_workflow")
_wf.propagate = False


def _setup_workflow_logger() -> None:
    if not settings.llm_workflow_log:
        return
    _wf.setLevel(logging.DEBUG)
    Path("logs").mkdir(exist_ok=True)
    if not _wf.handlers:
        h = RotatingFileHandler(
            "logs/llm_workflow.log",
            maxBytes=100 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        _wf.addHandler(h)


_setup_workflow_logger()

_SEP = "=" * 80


def _log_llm_call(
    *,
    stage: str,
    user_id: int | None,
    model: str,
    messages: list[dict],
    response: str,
    latency: float,
    tokens_in: int | None,
    tokens_out: int | None,
    thinking_tokens: int = 0,
    remaining: int | None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    uid_str = str(user_id) if user_id is not None else "unknown"

    lines = [
        "",
        _SEP,
        f"{now}  |  stage={stage}  |  user={uid_str}  |  model={model}",
        _SEP,
        f"--- INPUT [{len(messages)} messages] ---",
    ]

    for i, msg in enumerate(messages):
        role = msg["role"].upper()
        content = msg["content"]
        lines.append(f"\n[{i}] {role} ({len(content)} chars)")
        lines.append(content)

    lines += [
        "",
        f"--- OUTPUT ({len(response)} chars) ---",
        "",
        response,
        "",
        "--- STATS ---",
    ]

    if tokens_in is not None:
        lines.append(f"Prompt tokens    : {tokens_in}")
        lines.append(f"Completion tokens: {tokens_out}")
        if thinking_tokens:
            lines.append(f"Thinking tokens  : {thinking_tokens}")
        lines.append(f"Total tokens     : {(tokens_in or 0) + (tokens_out or 0)}")
    lines.append(f"Latency          : {latency:.3f}s")
    if remaining is not None:
        lines.append(f"Remaining req/day: {remaining}")

    lines.append(_SEP)

    _wf.debug("\n".join(lines))


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _to_google(messages: list[dict]) -> tuple[dict | None, list[dict]]:
    """Convert OpenAI-format messages to Google AI Studio format.

    Returns (systemInstruction dict or None, contents list).
    - First system message → systemInstruction (excluded from contents)
    - role "assistant" → "model"
    - content str → parts: [{"text": content}]
    """
    system = None
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            if system is None:
                system = {"parts": [{"text": msg["content"]}]}
            continue
        role = "model" if msg["role"] == "assistant" else msg["role"]
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    return system, contents


def _format_articles(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        desc = a.get("description", "")
        if desc:
            lines.append(f"{i}. {a['title']}\n   {desc}")
        else:
            lines.append(f"{i}. {a['title']}")
    return "\n\n".join(lines)


async def _chat(
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
    *,
    user_id: int | None = None,
    stage: str = "",
) -> str:
    system, contents = _to_google(messages)

    body: dict = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
            "thinkingConfig": _THINKING_CONFIG,
        },
    }
    if system:
        body["systemInstruction"] = system

    url = f"{_GOOGLE_BASE}/{model}:generateContent?key={settings.google_api_key}"

    last_exc: Exception | None = None
    t0 = 0.0
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(2 ** attempt)  # 2s, 4s
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, json=body)
        if r.status_code < 500:
            break
        last_exc = httpx.HTTPStatusError(
            f"Server error '{r.status_code}' (attempt {attempt + 1}/3)",
            request=r.request,
            response=r,
        )
        logger.warning("Google API %d on attempt %d, retrying...", r.status_code, attempt + 1)
    else:
        raise last_exc  # type: ignore[misc]
    latency = time.monotonic() - t0

    r.raise_for_status()
    data = r.json()

    try:
        parts = data["candidates"][0]["content"]["parts"]
        answer = "\n".join(p["text"] for p in parts if not p.get("thought", False))
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected API response structure: %s", data)
        raise ValueError("Empty or blocked response from Google API") from exc

    usage = data.get("usageMetadata", {})
    if settings.llm_workflow_log:
        _log_llm_call(
            stage=stage,
            user_id=user_id,
            model=model,
            messages=messages,
            response=answer,
            latency=latency,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
            thinking_tokens=usage.get("thoughtsTokenCount", 0),
            remaining=None,
        )
    return answer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class NoArticlesError(Exception):
    pass


async def get_digest(user_id: int, model: str) -> tuple[str, list[dict]]:
    articles = await news_fetcher.fetch_all(days=7)
    if not articles:
        raise NoArticlesError
    prompt = DIGEST_PROMPT_TEMPLATE.format(
        days=7,
        articles=_format_articles(articles),
    )
    raw_response = await _chat(
        model,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        user_id=user_id,
        stage="digest",
    )
    return raw_response, articles


async def deep_dive_summary(
    article: dict, content: str, model: str, user_id: int | None = None
) -> str:
    prompt = DEEP_DIVE_SUMMARY_PROMPT.format(
        title=article["title"],
        content=content,
    )
    return await _chat(
        model,
        [
            {"role": "system", "content": DEEP_DIVE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        user_id=user_id,
        stage=f"deep_dive_summary:{article.get('arxiv_id', article['title'][:40])}",
    )


async def deep_dive_followup(
    user_message: str,
    article: dict,
    article_content: str,
    model: str,
    user_id: int | None = None,
) -> str:
    system = DEEP_DIVE_FOLLOWUP_SYSTEM.format(
        title=article["title"],
        content=article_content,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    return await _chat(
        model,
        messages,
        user_id=user_id,
        stage=f"deep_dive_followup:{article.get('arxiv_id', article['title'][:40])}",
    )


async def search_articles(
    question: str,
    articles: list[dict],
    model: str,
    user_id: int | None = None,
) -> str:
    prompt = ARTICLE_SEARCH_PROMPT.format(
        days=7,
        count=len(articles),
        articles=_format_articles(articles),
        question=question,
    )
    return await _chat(
        model,
        [
            {"role": "system", "content": ARTICLE_SEARCH_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        user_id=user_id,
        stage="article_search",
    )
