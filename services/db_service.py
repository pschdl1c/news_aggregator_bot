import aiosqlite
from pathlib import Path

from config.settings import settings

_DB_PATH = settings.database_path
_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


async def init_db() -> None:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript(schema)
        await db.commit()


async def is_whitelisted(user_id: int) -> bool:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def add_to_whitelist(user_id: int, username: str | None, added_by: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO whitelist (user_id, username, added_by) VALUES (?, ?, ?)",
            (user_id, username, added_by),
        )
        await db.commit()


async def remove_from_whitelist(user_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
        await db.commit()


async def list_whitelist() -> list[tuple[int, str | None]]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username FROM whitelist ORDER BY added_at"
        ) as cursor:
            return await cursor.fetchall()


async def save_chat_message(user_id: int, role: str, content: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await db.commit()


async def get_chat_history(user_id: int, limit: int) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content
                FROM chat_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]


async def clear_chat_history(user_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_user_model(user_id: int) -> str:
    from config.settings import settings
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT model FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else settings.default_model


async def set_user_model(user_id: int, model: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, model) VALUES (?, ?)",
            (user_id, model),
        )
        await db.commit()
