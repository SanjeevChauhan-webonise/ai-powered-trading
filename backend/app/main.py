import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.agents.orchestrator import mark_interrupted
from app.api import auth, backtests, datasets, expiries, health, knowledge, models, paper, runs, strategies
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.logging import setup_logging
from app.core.tracing import setup_tracing
from app.rag.startup import start_autoingest

settings = get_settings()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_tracing(settings)
    try:
        n = await run_in_threadpool(mark_interrupted, getattr(app.state, "session_factory", get_session))
        if n:
            logging.getLogger(__name__).warning("marked %d interrupted pipeline run(s) as failed", n)
    except Exception as e:  # DB not ready must not block startup
        logging.getLogger(__name__).warning("could not check for interrupted runs: %s", e)
    if settings.rag_autoingest:
        start_autoingest(settings)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Educational options backtesting research prototype. Not financial advice.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)  # open: used by the orchestrator / uptime checks
app.include_router(auth.router)  # open: register and login
_login = [Depends(get_current_user)]  # everything else needs a logged-in user
for _router in (datasets, strategies, backtests, models, knowledge, runs, expiries, paper):
    app.include_router(_router.router, dependencies=_login)
