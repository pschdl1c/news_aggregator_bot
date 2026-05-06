import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("ADMIN_USER_ID", "123")

from bot.middlewares.auth import WhitelistMiddleware


@pytest.mark.asyncio
async def test_admin_passes_through():
    middleware = WhitelistMiddleware()
    handler = AsyncMock(return_value="ok")

    user = MagicMock()
    user.id = 123
    user.username = "admin"

    event = MagicMock()
    data = {"event_from_user": user, "bot": AsyncMock()}

    result = await middleware(handler, event, data)
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_whitelisted_user_passes():
    middleware = WhitelistMiddleware()
    handler = AsyncMock(return_value="ok")

    user = MagicMock()
    user.id = 456
    user.username = "whitelisted"

    event = MagicMock()
    data = {"event_from_user": user, "bot": AsyncMock()}

    with patch("bot.middlewares.auth.db_service.is_whitelisted", AsyncMock(return_value=True)):
        result = await middleware(handler, event, data)

    assert result == "ok"


@pytest.mark.asyncio
async def test_unknown_user_blocked():
    middleware = WhitelistMiddleware()
    handler = AsyncMock(return_value="ok")

    user = MagicMock()
    user.id = 789
    user.username = "stranger"

    bot_mock = AsyncMock()
    event = MagicMock(spec=[])
    data = {"event_from_user": user, "bot": bot_mock}

    with patch("bot.middlewares.auth.db_service.is_whitelisted", AsyncMock(return_value=False)):
        result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()
    bot_mock.send_message.assert_awaited_once()
