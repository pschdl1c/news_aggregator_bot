import os
import pytest

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("ADMIN_USER_ID", "123")

from services import db_service

TEST_DB = ":memory:"


@pytest.fixture(autouse=True)
def patch_db_path(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_service, "_DB_PATH", db_file)


@pytest.mark.asyncio
async def test_init_db():
    await db_service.init_db()


@pytest.mark.asyncio
async def test_whitelist():
    await db_service.init_db()
    assert not await db_service.is_whitelisted(999)
    await db_service.add_to_whitelist(999, "testuser", 123)
    assert await db_service.is_whitelisted(999)
    await db_service.remove_from_whitelist(999)
    assert not await db_service.is_whitelisted(999)


@pytest.mark.asyncio
async def test_chat_history():
    await db_service.init_db()
    user_id = 2
    await db_service.save_chat_message(user_id, "user", "hello")
    await db_service.save_chat_message(user_id, "assistant", "hi")
    history = await db_service.get_chat_history(user_id, limit=10)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    await db_service.clear_chat_history(user_id)
    history = await db_service.get_chat_history(user_id, limit=10)
    assert len(history) == 0
