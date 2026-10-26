FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    UV_HTTP_TIMEOUT=300 UV_HTTP_RETRIES=10
COPY pyproject.toml ./
# the cache mount keeps downloaded wheels, so a retry after a network timeout resumes instead of starting over
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-install-project
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
