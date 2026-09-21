"""FastAPI application: CORS, startup loading (lifespan) and routing.

Run from the backend/ folder:
    uvicorn app.main:app --reload
Then open http://localhost:8000/docs
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import query
from app.core.config import get_settings
from app.services.generation import GenerationService
from app.services.retrieval import RetrievalService, VectorStoreError
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the vector store, embedding model and LLM client ONCE at startup, not on every request."""
    settings = get_settings()
    setup_logging(settings.log_level)

    app.state.retrieval = None
    app.state.generation = None
    app.state.startup_error = None

    try:
        retrieval = RetrievalService.load(settings)
        app.state.retrieval = retrieval
        app.state.generation = GenerationService(settings, retrieval.store_config)
    except VectorStoreError as exc:
        # Do not crash: keep the API up so /health can explain what is wrong.
        logger.error("Startup problem: %s", exc)
        app.state.startup_error = str(exc)

    yield

    app.state.retrieval = None
    app.state.generation = None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Retrieval-Augmented Generation API. `POST /query` retrieves the most relevant document chunks "
            "from a persisted ChromaDB store, asks a local Ollama LLM to answer using only those chunks, "
            "and returns the answer with its cited sources."
        ),
        lifespan=lifespan,
    )

    # CORS: only the frontend origins listed in CORS_ORIGINS may call the API from a browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
        return response

    app.include_router(query.router)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": settings.app_name, "docs": "/docs", "health": "/health"}

    return app


app = create_app()
