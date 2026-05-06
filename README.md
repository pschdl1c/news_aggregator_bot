# News Aggregator Bot

Telegram-бот для мониторинга новостей об AI, LLM и Machine Learning. Агрегирует статьи с [HuggingFace Daily Papers](https://huggingface.co/papers), формирует дайджест через Google AI Studio и позволяет погружаться в любую статью.

## Возможности

- **Дайджест за неделю** — модель отбирает 5–7 наиболее интересных статей из всего потока за 7 дней
- **Deep dive** — скачивает полный текст статьи (ar5iv/arXiv HTML) и делает структурированный анализ: проблема, метод, результаты, вклад
- **Вопросы по статье** — после анализа можно задавать любые вопросы; модель отвечает строго по тексту
- **Поиск** — напишите запрос в чат, и модель найдёт релевантные статьи среди всех за неделю
- **Whitelist** — доступ только по явному одобрению; неизвестный пользователь отправляет запрос администратору

## Стек

| | |
|---|---|
| Runtime | Python 3.12, [uv](https://docs.astral.sh/uv/) |
| Bot framework | aiogram 3.x |
| LLM backend | Google AI Studio REST API (Gemma 4) |
| HTTP | httpx (async) |
| Database | SQLite + aiosqlite |
| Article scraping | trafilatura + ar5iv |
| Deploy | Docker + docker-compose |

## Быстрый старт

```bash
# 1. Зависимости
uv sync --dev

# 2. Конфигурация
cp .env.example .env
# заполните .env (см. раздел ниже)

# 3. Запуск
uv run python -m bot.main
```

## Конфигурация (.env)

```env
BOT_TOKEN=          # токен от @BotFather
GOOGLE_API_KEY=     # ключ Google AI Studio (aistudio.google.com)
ADMIN_USER_ID=      # ваш Telegram user_id

DATABASE_PATH=./data/bot.db   # путь к SQLite-базе
LLM_WORKFLOW_LOG=false        # true — логировать полный ввод/вывод LLM в logs/llm_workflow.log
```

## Docker

```bash
git clone https://github.com/<username>/news_aggregator_bot.git
cd news_aggregator_bot
cp .env.example .env
nano .env
docker compose up -d --build
```

Обновление: `git pull && docker compose up -d --build`

Данные (SQLite) сохраняются в named volume `bot_data` и не теряются при пересборке.

## Команды бота

| Команда | Доступ | Описание |
|---|---|---|
| `/start` | whitelist | главное меню |
| `/reset` | whitelist | сбросить состояние сессии |
| `/add_user <id>` | admin | добавить пользователя в whitelist |
| `/remove_user <id>` | admin | удалить из whitelist |
| `/list_users` | admin | показать whitelist |

## Тесты

```bash
uv run pytest -v
```

## TODO

- **Заменить `MemoryStorage` на Redis** (`bot/main.py`). FSM-состояние (статьи, текст deep dive, дайджест) хранится в RAM без TTL и сбрасывается при каждом рестарте. При росте нагрузки — давление на память, невозможность горизонтального масштабирования. Решение: `aiogram-storage-redis` + Redis-сервис в docker-compose + TTL сессии ~2 часа.

## Структура проекта

```
bot/
  handlers/        # Telegram-хендлеры (digest, deep_dive, chat, model, start)
  middlewares/     # whitelist-проверка
  keyboards/       # inline-клавиатуры
  states/          # FSM-состояния
  utils.py         # разбивка длинных сообщений
services/
  llm_service.py   # вызовы Google AI Studio
  news_fetcher.py  # агрегация HuggingFace Daily Papers
  scraper.py       # получение полного текста статьи
  db_service.py    # CRUD для SQLite
  prompts.py       # все промпты
config/
  settings.py      # Pydantic Settings + каталог моделей
db/
  schema.sql       # DDL
```
