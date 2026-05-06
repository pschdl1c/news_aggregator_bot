import logging
import re

from aiogram.types import Message, InlineKeyboardMarkup, LinkPreviewOptions

logger = logging.getLogger(__name__)

_ARTICLE_RE = re.compile(r'###(?:ARTICLE_)?(\d+)###\s*\n?(.*?)(?=###(?:ARTICLE_)?\d+###|\Z)', re.DOTALL)


def parse_digest_response(raw: str, articles: list[dict]) -> list[dict] | None:
    matches = _ARTICLE_RE.findall(raw)
    if not matches:
        return None
    result = []
    for num_str, summary in matches:
        idx = int(num_str) - 1
        if 0 <= idx < len(articles):
            result.append({
                **articles[idx],
                "summary": summary.strip(),
                "display_num": len(result) + 1,
            })
    return result if result else None


def format_digest_html(items: list[dict]) -> str:
    parts = []
    for item in items:
        title_link = f'<a href="{item["url"]}">{item["title"]}</a>'
        parts.append(f'{item["display_num"]}. {title_link}\n{item["summary"]}')
    return "\n\n".join(parts)

TG_MAX_LEN = 4096

_LINK_PREVIEW_DISABLED = LinkPreviewOptions(is_disabled=True)


def _split_text(text: str) -> list[str]:
    if len(text) <= TG_MAX_LEN:
        return [text]

    chunks: list[str] = []
    while len(text) > TG_MAX_LEN:
        split_at = text.rfind('\n\n', 0, TG_MAX_LEN)
        if split_at != -1:
            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()
            continue
        split_at = text.rfind('\n', 0, TG_MAX_LEN)
        if split_at > 0:
            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip('\n')
            continue
        chunks.append(text[:TG_MAX_LEN])
        text = text[TG_MAX_LEN:]

    if text.strip():
        chunks.append(text.strip())

    return chunks


def _has_hyperlink(text: str) -> bool:
    return '<a href=' in text or 'https://' in text or 'http://' in text


async def send_long_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    chunks = _split_text(text)
    link_preview = _has_hyperlink(text)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await message.answer(
                chunk,
                reply_markup=markup,
                parse_mode=parse_mode,
                link_preview_options=_LINK_PREVIEW_DISABLED if link_preview else None,
            )
        except Exception:
            logger.exception("Failed to send chunk %d/%d", i + 1, len(chunks))
            raise
