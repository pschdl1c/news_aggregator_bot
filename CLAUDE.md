# News Aggregator Bot

Telegram-бот на Python для мониторинга новостей об AI, LLM, ML с интеграцией Google AI Studio и HuggingFace Daily Papers.

## Стек

- **Python 3.12+**
- **uv** — менеджер пакетов и виртуального окружения
- **aiogram 3.x** — async Telegram bot framework
- **httpx** — async HTTP-клиент (в т.ч. для запросов к Google AI Studio REST API)
- **SQLite + aiosqlite** — хранение истории диалогов, whitelist, настроек пользователя
- **trafilatura** — извлечение текста статей из HTML
- **Docker + docker-compose** — деплой

## Окружение (uv)

```bash
# Создать окружение и установить зависимости
uv venv .venv
uv sync --dev

# Запуск бота
uv run python -m bot.main

# Запуск тестов
uv run pytest

# Добавить зависимость
uv add <package>
```

Зависимости хранятся в `pyproject.toml`, lockfile — `uv.lock`.

## Структура проекта

```
news_aggregator_bot/
├── bot/
│   ├── main.py                  # точка входа, инициализация dp и bot
│   ├── handlers/
│   │   ├── start.py             # /start, главное меню; admin-команды (/add_user и др.)
│   │   ├── digest.py            # кнопка "Дайджест за неделю"; парсинг ответа LLM
│   │   ├── deep_dive.py         # кнопки 🔍N — deep dive в конкретную статью
│   │   ├── chat.py              # follow-up чат после дайджеста (BotStates.chat)
│   │   └── model.py             # выбор LLM-модели через inline-кнопки
│   ├── keyboards/
│   │   └── main_menu.py         # main_menu(), back_to_menu(), deep_dive_keyboard()
│   ├── middlewares/
│   │   └── auth.py              # whitelist-проверка перед каждым апдейтом
│   ├── states/
│   │   └── chat.py              # FSM: BotStates.chat, BotStates.deep_dive
│   └── utils.py                 # send_long_message (разбивка на чанки по 4096)
├── services/
│   ├── news_fetcher.py          # агрегация: HuggingFace Daily Papers
│   ├── llm_service.py           # все вызовы Google AI Studio API
│   ├── scraper.py               # получение текста статьи (ar5iv для arXiv, trafilatura для остальных)
│   ├── db_service.py            # CRUD операции с SQLite
│   └── prompts.py               # все промпты вынесены сюда
├── db/
│   └── schema.sql               # DDL: chat_history, whitelist, user_settings
├── config/
│   └── settings.py              # Pydantic Settings + MODEL_CATALOGUE
├── logs/                        # директория логов (gitignored)
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Источники новостей

Новости агрегируются в `news_fetcher.py`:

- **HuggingFace Daily Papers** — `huggingface.co/api/daily_papers?date=YYYY-MM-DD` за каждый день диапазона. Возвращает curated AI-статьи (arXiv) с полным abstract в `summary`. Параллельные запросы, дедупликация по `arxiv_id`.

Результаты передаются в LLM для синтеза дайджеста.

## Получение текста статьи (scraper.py)

Для deep dive нужен полный текст. Логика:

1. Из URL извлекается arXiv ID (паттерны: `arxiv.org/abs/{id}`, `huggingface.co/papers/{id}`)
2. Если ID найден → запрос к **ar5iv** (`arxiv.org/html/{id}`, затем `ar5iv.labs.arxiv.org/html/{id}`)
3. Cookie-wall detection: если текст < 200 символов или содержит ≥ 2 фразы-маркера (cookie consent) → вернуть `None`
4. При `None` из scraper — `deep_dive.py` использует `description` (abstract из HF feed) как контент
5. Текст **не обрезается** — полная статья передаётся в модель (контекст Gemma 4 = 128K токенов)

## База данных (SQLite)

```sql
CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,       -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE whitelist (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by INTEGER
);

CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `chat_history` — что и когда сохраняется

Таблица используется как лог взаимодействий; LLM контекст из неё не читается (каждый вызов независим).

| Сценарий | role | Что сохраняется | Где |
|---|---|---|---|
| Дайджест сгенерирован | `assistant` | HTML-текст дайджеста | `digest.py` |
| Поиск по статьям | `user` | Запрос пользователя | `chat.py` |
| Вопрос по статье (deep dive) | `user` | Вопрос пользователя | `deep_dive.py` |

История не очищается — хранится как постоянный лог. `/reset` сбрасывает только FSM-состояние сессии.

### `whitelist` — как формируется

Два способа добавить пользователя:

1. **Вручную через команды** (только admin):
   - `/add_user <user_id>` — добавить
   - `/remove_user <user_id>` — удалить

2. **Через inline-одобрение** (основной flow):
   - Неизвестный пользователь пишет боту → `WhitelistMiddleware` блокирует апдейт и отправляет admin'у сообщение с кнопками «✅ Одобрить / ❌ Отклонить»
   - Admin нажимает «Одобрить» → `cb_approve_user` в `start.py` → `add_to_whitelist()`
   - Admin — всегда пропускается без проверки БД (`user_id == ADMIN_USER_ID`)

### `user_settings` — выбранная модель

- Читается в начале каждого LLM-вызова (`get_user_model`). Если записи нет — используется `default_model` из `.env`.
- Записывается при нажатии «⚙️ Сменить модель» → `cb_set_model` в `model.py`.

## LLM-бэкенд: Google AI Studio

Запросы делаются напрямую через `httpx` к REST API Google AI Studio:

```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}
```

Используется `thinkingConfig: {thinkingLevel: "MINIMAL"}` для минимизации thinking-токенов (0 tok). Официальный Python SDK (`google-genai`) **не используется** — он не поддерживает `thinkingLevel` для Gemma 4, что приводит к нежелательным thinking-токенам при каждом запросе.

Формат сообщений конвертируется из OpenAI-формата (user/assistant) в Google-формат (user/model + systemInstruction) через `_to_google()` в `llm_service.py`.

### Каталог моделей (`config/settings.py`)

```python
MODEL_CATALOGUE = [
    {"id": "gemma-4-31b-it",    "tier": "S", "input_token_limit": 131072, "output_token_limit": 8192},
    {"id": "gemma-4-26b-a4b-it","tier": "A", "input_token_limit": 131072, "output_token_limit": 8192},
]
```

Пользователь выбирает модель через `⚙️ Сменить модель` → сохраняется в `user_settings`. Дефолт — `gemma-4-31b-it`.

### Промпты (`services/prompts.py`)

| Промпт | Функция | Роль | Содержание |
|---|---|---|---|
| `SYSTEM_PROMPT` | `get_digest` | system | Роль ассистента по AI/ML новостям, без markdown, на русском |
| `DIGEST_PROMPT_TEMPLATE` | `get_digest` | user | Все статьи за 7 дней (заголовок + полный abstract), задача выбрать 5–7 лучших, формат `###N###` |
| `ARTICLE_SEARCH_SYSTEM` | `search_articles` | system | Роль поисковика по списку статей |
| `ARTICLE_SEARCH_PROMPT` | `search_articles` | user | Все статьи за 7 дней + вопрос пользователя; модель возвращает релевантные в формате `###N###` или «не найдено» |
| `DEEP_DIVE_SYSTEM_PROMPT` | `deep_dive_summary` | system | Жёсткие правила: только из текста статьи, не додумывать |
| `DEEP_DIVE_SUMMARY_PROMPT` | `deep_dive_summary` | user | Полный текст статьи + структура анализа (проблема / метод / результаты / вклад) |
| `DEEP_DIVE_FOLLOWUP_SYSTEM` | `deep_dive_followup` | system | Полный текст статьи встроен в system-сообщение; отвечает на вопросы строго по тексту |

Схема вызовов:

```
Дайджест            → SYSTEM_PROMPT + DIGEST_PROMPT_TEMPLATE (все статьи за 7 дней)
Поиск по статьям    → ARTICLE_SEARCH_SYSTEM + ARTICLE_SEARCH_PROMPT (все статьи + вопрос)
Deep dive анализ    → DEEP_DIVE_SYSTEM_PROMPT + DEEP_DIVE_SUMMARY_PROMPT(текст статьи)
Deep dive вопрос    → DEEP_DIVE_FOLLOWUP_SYSTEM(текст статьи) + вопрос   # без истории, каждый вопрос независим
```

### Токены и контекст

- В промпт дайджеста и поиска: все статьи за 7 дней с полными abstract (без обрезки)
- Для deep dive: полный текст статьи без обрезки (Gemma 4 — 128K контекст)
- Один батч-запрос для дайджеста и поиска

## Архитектура по сценариям

### Сценарий 1: Дайджест за неделю

```
[news_fetcher] → HuggingFace Daily Papers (7 дней) → все статьи (без лимита)
[llm_service]  → single prompt: выбрать 5-7 лучших из всех, формат ###N###
[digest.py]    → parse_digest_response(), format_digest_html() → HTML с ссылками
[state]        → сохраняются all_articles (все), digest_articles (5-7), digest_text
[handler]      → отправить + кнопки 🔍1 🔍2 ... → BotStates.chat
```

### Сценарий 2: Deep Dive в статью

```
[deep_dive.py] → пользователь нажал 🔍N → берёт article из state
[scraper]      → ar5iv HTML → trafilatura extract → полный текст статьи
[llm_service]  → deep_dive_summary: структурированный анализ (проблема/метод/результаты/вклад)
[handler]      → отправить анализ + "Можете задавать вопросы" → BotStates.deep_dive
```

### Сценарий 3: Поиск по статьям (BotStates.chat)

```
[chat.py]      → пользователь пишет вопрос ("есть ли статьи по безопасности?")
[llm_service]  → search_articles(вопрос, all_articles) — модель ищет в полном списке
[chat.py]      → если ###N### в ответе → parse_digest_response() → mini-дайджест с 🔍
               → если нет совпадений → plain text + кнопка ↩️ К дайджесту
[state]        → digest_articles обновляется, кнопки 🔍 ведут на найденные статьи
```

### Сценарий 4: Follow-up вопросы по статье (BotStates.deep_dive)

```
[deep_dive.py] → сообщение пользователя в FSM state deep_dive
[llm_service]  → deep_dive_followup(вопрос, текст статьи) — без истории диалога
[handler]      → отправить ответ + кнопки ↩️ К дайджесту / 🏠 В главное меню
```

## Авторизация и whitelist

- **Middleware `auth.py`** проверяет каждый апдейт ДО хендлеров.
- Если `user_id` не в whitelist и не `ADMIN_USER_ID` → отказ + уведомление админу с кнопками "Одобрить / Отклонить".
- Whitelist хранится в **SQLite** (`whitelist` таблица). Управляется через команды `/add_user`, `/remove_user`.

## Логирование

- **`RotatingFileHandler`**: `logs/bot.log` (max 200MB, 2 бэкапа), `logs/errors.log` (ERROR+, 50MB).
- Также `StreamHandler` для консоли.
- Логируется: `user_id`, тип события, timestamp. Текст сообщений не логируется.
- Формат: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`

### Workflow-лог LLM-вызовов

`logs/llm_workflow.log` — полный ввод/вывод каждого LLM-вызова с метриками токенов и латентностью. **По умолчанию отключён.** Включается через `.env`:

```env
LLM_WORKFLOW_LOG=true
```

При `false` файл не создаётся, обработчик не инициализируется.

## Конфигурация (.env)

```env
# Telegram
BOT_TOKEN=

# Google AI Studio
GOOGLE_API_KEY=

# Admin
ADMIN_USER_ID=

# DB
DATABASE_PATH=./data/bot.db

# Logging (опционально)
LLM_WORKFLOW_LOG=false
```

## Docker

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen
COPY . .
RUN mkdir -p data logs
CMD ["uv", "run", "python", "-m", "bot.main"]
```

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
```

## Команды бота

| Команда | Доступ | Описание |
|---|---|---|
| `/start` | whitelist | главное меню |
| `/reset` | whitelist | сбросить контекст диалога |
| `/add_user <user_id>` | admin only | добавить в whitelist |
| `/remove_user <user_id>` | admin only | убрать из whitelist |
| `/list_users` | admin only | показать whitelist |

## Главное меню

```
┌─────────────────────────────────────┐
│  📰 Дайджест за неделю              │
├─────────────────────────────────────┤
│  ⚙️ Сменить модель                  │
├─────────────────────────────────────┤
│  ℹ️ О боте                          │
└─────────────────────────────────────┘
```

«О боте» показывает описание всех возможностей бота (дайджест, deep dive, поиск по статьям, смена модели) — текст задан константой `_ABOUT_TEXT` в `bot/handlers/start.py`.

После дайджеста появляются кнопки `🔍1 🔍2 ... 🔍N` (deep dive в каждую статью) и `🏠 В главное меню`.

### Формат сообщения дайджеста

```
📊 Статей за 7 дней: N

Наиболее интересные и релевантные:

1. <ссылка> Название
   Описание от модели.
...

──────────
💬 Напишите запрос — и я найду подходящие статьи среди всех N.
```

Шапка и подпись формируются в `cb_digest()` (`bot/handlers/digest.py`) вокруг HTML от `format_digest_html()`. В подписи указывается реальное количество статей за неделю.

## Правила разработки

- Весь I/O — async (aiosqlite, httpx, aiogram).
- Secrets только через `.env`, никогда в коде.
- Промпты в `services/prompts.py`, не инлайнятся в логику.
- Тесты покрывают: auth middleware, llm_service (mock `_chat`), db_service.
- `requirements.txt` с фиксированными версиями (`==`).
