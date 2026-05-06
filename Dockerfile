FROM python:3.12-slim

RUN pip install --no-cache-dir uv \
    && groupadd -r botuser \
    && useradd -r -g botuser -d /app botuser

WORKDIR /app
RUN chown botuser:botuser /app

USER botuser

COPY --chown=botuser:botuser pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-cache

COPY --chown=botuser:botuser . .
RUN mkdir -p data logs

CMD ["uv", "run", "python", "-m", "bot.main"]
