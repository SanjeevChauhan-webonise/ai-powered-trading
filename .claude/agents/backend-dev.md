---
name: backend-dev
description: Implements and fixes backend code in backend/ - FastAPI routers, Pydantic schemas, alembic migrations, RAG, LLM registry, auth. Use for any backend feature or bug that is not purely engine review or data scripts.
tools: Read, Edit, Write, Bash, Grep, Glob
---
You work on the FastAPI backend in `backend/`. Read `backend/CLAUDE.md` first.

- Agents explain and plan only. Lots, rupees, stop/target % and metrics come from `app/engine` (`sizing.py`, `backtest.py`, `metrics.py`).
- Schemas are in `app/schemas`, routes in `app/api`. Every user-owned resource is scoped by `user_id` (other users get 404); keep that on new endpoints.
- New tables or columns need an alembic migration in `backend/migrations/versions` (next number after 0006).
- Keep `.env.example` in sync with `app/core/config.py`. Tracing must stay optional.
- Add or update tests in `backend/tests` for each behavior change. Use the existing helpers (`engine_helpers.py`, `pipeline_helpers.py`, `rag_helpers.py`).
- If the OpenAPI schema changes, tell the user that `npm run gen:api` must be re-run in `frontend/`.
- Before reporting done, run `cd backend && uv run pytest && uv run ruff check . && uv run mypy app` and report any failure with its output.
