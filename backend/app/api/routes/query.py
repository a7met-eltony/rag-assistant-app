"""Endpoints: GET /health and POST /query."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.query import HealthResponse, QueryRequest, QueryResponse
from app.services.generation import GenerationError, GenerationService, OllamaUnavailableError
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)
router = APIRouter()


# ----------------------------------------------------------------------------- dependencies
# The services are created ONCE at startup (lifespan in main.py) and stored on app.state.
def get_retrieval_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", None) or "Vector store is not loaded."
        raise HTTPException(status_code=503, detail=detail)
    return service


def get_generation_service(request: Request) -> GenerationService:
    service = getattr(request.app.state, "generation", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Generation service is not available.")
    return service


# ----------------------------------------------------------------------------- endpoints
@router.get("/health", response_model=HealthResponse, tags=["system"], summary="Service health")
def health(request: Request) -> HealthResponse:
    """Always answers 200. `status` is `degraded` when the vector store or Ollama is not ready."""
    retrieval = getattr(request.app.state, "retrieval", None)
    generation = getattr(request.app.state, "generation", None)

    ollama_reachable, model_available = (False, False)
    if generation is not None:
        ollama_reachable, model_available = generation.check_ollama()

    problems = []
    if retrieval is None:
        problems.append(getattr(request.app.state, "startup_error", None) or "Vector store is not loaded.")
    if not ollama_reachable:
        problems.append("Ollama is not reachable.")
    elif not model_available:
        problems.append(f"Model '{generation.model}' is not installed (ollama pull {generation.model}).")

    return HealthResponse(
        status="ok" if not problems else "degraded",
        vector_store_loaded=retrieval is not None,
        vector_store_dir=str(retrieval.store_dir) if getattr(retrieval, "store_dir", None) else None,
        num_chunks=retrieval.num_chunks if retrieval is not None else None,
        embedding_model=retrieval.embedding_model if retrieval is not None else None,
        ollama_reachable=ollama_reachable,
        ollama_model=generation.model if generation is not None else None,
        model_available=model_available,
        detail=" ".join(problems) or None,
    )


@router.post("/query", response_model=QueryResponse, tags=["rag"], summary="Ask a question about the documents")
def query(
    payload: QueryRequest,
    retrieval: RetrievalService = Depends(get_retrieval_service),
    generation: GenerationService = Depends(get_generation_service),
) -> QueryResponse:
    """retrieve -> build prompt -> call the local LLM -> return a grounded, cited answer.

    Declared with `def` (not `async def`) on purpose: retrieval and the LLM call are blocking,
    so FastAPI runs this in a worker thread instead of freezing the event loop.
    """
    hits = retrieval.retrieve(payload.question)
    logger.info("Question (%d chars): top similarity %.3f from %s",
                len(payload.question), hits[0].similarity if hits else 0.0, hits[0].source if hits else "-")

    try:
        result = generation.generate(payload.question, hits)
    except OllamaUnavailableError as exc:
        logger.error("Ollama unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GenerationError as exc:
        logger.error("Generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return QueryResponse(answer=result.answer, sources=result.sources)
