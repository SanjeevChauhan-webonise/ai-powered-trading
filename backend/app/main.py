import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.agents.orchestrator import mark_interrupted
from app.api import backtests, datasets, health, knowledge, models, runs, strategies
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
app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(strategies.router)
app.include_router(backtests.router)
app.include_router(models.router)
app.include_router(knowledge.router)
app.include_router(runs.router)
