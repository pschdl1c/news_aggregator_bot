import logging
import re
from urllib.parse import urlparse

import httpx
import trafilatura

logger = logging.getLogger(__name__)

_ALLOWED_DOMAINS = frozenset({
    "arxiv.org",
    "ar5iv.labs.arxiv.org",
    "huggingface.co",
})

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|html)/|huggingface\.co/papers/)(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)

# Признаки страницы-абстракта arxiv.org/abs/ — не полный текст статьи
_ABS_PAGE_MARKERS = frozenset({
    "view pdf html (experimental)",
    "bibliographic and citation tools",
    "arxivlabs is a framework",
})

# Признаки cookie-wall / consent-страниц
_JUNK_PHRASES = frozenset({
    "before you continue to google",
    "we use cookies",
    "cookie consent",
    "accept all cookies",
})


def _extract_arxiv_id(url: str) -> str | None:
    m = _ARXIV_ID_RE.search(url)
    return m.group(1) if m else None


def _is_abs_page(text: str) -> bool:
    lower = text.lower()
    return sum(1 for m in _ABS_PAGE_MARKERS if m in lower) >= 2


def _is_junk(text: str) -> bool:
    if len(text) < 200:
        return True
    lower = text.lower()
    return sum(1 for p in _JUNK_PHRASES if p in lower) >= 2


def _prepend_metadata(html: str, text: str) -> str:
    """Extract author/title metadata from HTML and prepend to body text."""
    meta = trafilatura.extract_metadata(html)
    parts = []
    if meta:
        if meta.title:
            parts.append(f"Заголовок: {meta.title}")
        if meta.author:
            parts.append(f"Авторы: {meta.author}")
    return "\n".join(parts) + "\n\n" + text if parts else text


async def _fetch_text(url: str) -> str | None:
    hostname = urlparse(url).hostname or ""
    if hostname not in _ALLOWED_DOMAINS:
        logger.warning("Blocked non-allowlisted domain: %s", hostname)
        return None
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            r = await client.get(url, headers=_HEADERS)
            r.raise_for_status()
        html = r.text
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
        )
        if text and not _is_junk(text):
            return _prepend_metadata(html, text)
        return None
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return None


async def fetch_article_text(url: str) -> str | None:
    arxiv_id = _extract_arxiv_id(url)
    if arxiv_id:
        # Пробуем официальный HTML arXiv, затем ar5iv
        for html_url in [
            f"https://arxiv.org/html/{arxiv_id}",
            f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
        ]:
            text = await _fetch_text(html_url)
            if text and not _is_abs_page(text):
                logger.info("HTML fetch ok url=%s len=%d", html_url, len(text))
                return text
            if text:
                logger.warning("Got abs-page content from %s, skipping", html_url)

        logger.warning("All HTML sources failed for arxiv_id=%s", arxiv_id)
        return None  # хендлер использует description (abstract из HF feed)

    # Для не-arXiv ссылок — обычный скрапинг
    return await _fetch_text(url)
