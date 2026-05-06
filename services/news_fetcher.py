import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

HF_PAPERS_URL = "https://huggingface.co/api/daily_papers"


async def _fetch_for_date(client: httpx.AsyncClient, date_str: str) -> list[dict]:
    try:
        r = await client.get(HF_PAPERS_URL, params={"date": date_str})
        r.raise_for_status()
        result = []
        for item in r.json():
            arxiv_id = item.get("paper", {}).get("id") or item.get("id", "")
            title = item.get("paper", {}).get("title") or item.get("title", "")
            summary = item.get("paper", {}).get("summary") or item.get("summary", "")
            if arxiv_id and title:
                result.append({
                    "title": title.strip(),
                    "url": f"https://huggingface.co/papers/{arxiv_id}",
                    "arxiv_id": arxiv_id,
                    "description": summary.strip(),
                    "source": "HuggingFace Daily Papers",
                })
        return result
    except Exception as e:
        logger.warning("HuggingFace fetch failed for %s: %s", date_str, e)
        return []


async def fetch_all(days: int = 7) -> list[dict]:
    dates = [
        (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days)
    ]
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*[_fetch_for_date(client, d) for d in dates])

    seen: set[str] = set()
    articles = []
    for day in results:
        for a in day:
            if a["arxiv_id"] not in seen:
                seen.add(a["arxiv_id"])
                articles.append(a)

    logger.info("fetch_all: %d unique articles over %d days", len(articles), days)
    return articles
