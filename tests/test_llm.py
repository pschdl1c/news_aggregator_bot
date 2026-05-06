import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("ADMIN_USER_ID", "123")

from services import llm_service

FAKE_ARTICLES = [
    {"title": "News 1", "url": "https://huggingface.co/papers/2501.00001", "arxiv_id": "2501.00001", "description": "desc 1", "source": "HuggingFace Daily Papers"},
    {"title": "News 2", "url": "https://huggingface.co/papers/2501.00002", "arxiv_id": "2501.00002", "description": "desc 2", "source": "HuggingFace Daily Papers"},
]

MODEL = "gemma-4-31b-it"


@pytest.mark.asyncio
async def test_get_digest_returns_text_and_articles():
    with patch("services.llm_service.news_fetcher.fetch_all", AsyncMock(return_value=FAKE_ARTICLES)):
        with patch("services.llm_service._chat", AsyncMock(return_value="###1###\nОписание")):
            text, articles = await llm_service.get_digest(1, MODEL)

    assert text == "###1###\nОписание"
    assert len(articles) == 2


@pytest.mark.asyncio
async def test_deep_dive_summary_calls_chat():
    article = {"title": "Test Paper", "url": "https://arxiv.org/abs/1234.56789"}
    content = "Abstract text about machine learning."

    with patch("services.llm_service._chat", AsyncMock(return_value="Анализ")) as mock_chat:
        result = await llm_service.deep_dive_summary(article, content, MODEL)

    assert result == "Анализ"
    assert mock_chat.called
