"""Generation: build the grounded prompt, call the local Ollama LLM, and validate the citations."""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import ollama

from app.core.config import Settings, resolve
from app.services.retrieval import Hit

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Prompts. Normally they are read from config.json (saved by the notebook in section 2.7)
# so the API behaves exactly like the notebook. These defaults are only a fallback.
# --------------------------------------------------------------------------------------
DEFAULT_REFUSAL = "I don't know based on the provided documents."

DEFAULT_SYSTEM_PROMPT = """You are a careful assistant that answers questions strictly from the numbered context excerpts provided.

Rules:
1. Use ONLY information found in the context. Never use outside knowledge, and never guess.
2. Cite the excerpt(s) that support every factual statement using square-bracket tags such as [S1] or [S2][S3].
3. If the context does not contain the answer, reply with exactly this sentence and nothing else: I don't know based on the provided documents.
4. Be concise: one to three sentences."""

DEFAULT_USER_TEMPLATE = """Context excerpts:
{context}

Question: {question}

Answer (remember the [S#] citations):"""

REFUSAL_PATTERN = re.compile(
    r"(don.?t know|do not know|not (?:contain|mention|specif|provide|includ)|no (?:relevant )?information|cannot (?:be )?(?:found|determined))",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------------------
# Errors (mapped to HTTP status codes in the route)
# --------------------------------------------------------------------------------------
class GenerationError(RuntimeError):
    """The LLM call failed for a reason other than being unreachable. -> HTTP 502."""


class OllamaUnavailableError(GenerationError):
    """Ollama is not reachable or the model is not installed. -> HTTP 503."""


# --------------------------------------------------------------------------------------
# Pure helpers (easy to unit-test)
# --------------------------------------------------------------------------------------
def is_refusal(answer: str) -> bool:
    return bool(REFUSAL_PATTERN.search(answer))


def parse_citations(answer: str, n_hits: int) -> Tuple[List[int], List[int]]:
    """Extract [S#] tags (also '[S1, S2]'). Returns (valid_indices, invalid_indices)."""
    found = set()
    for group in re.findall(r"\[([^\]]*S\d+[^\]]*)\]", answer):
        found.update(int(n) for n in re.findall(r"S(\d+)", group))
    valid = sorted(i for i in found if 1 <= i <= n_hits)
    invalid = sorted(i for i in found if not 1 <= i <= n_hits)
    return valid, invalid


def build_context(hits: List[Hit]) -> str:
    """Number the chunks so the model can cite them as [S1], [S2], ..."""
    blocks = []
    for i, hit in enumerate(hits, start=1):
        page = f", page {hit.page}" if hit.page else ""
        blocks.append(f"[S{i}] (source: {hit.source}{page})\n{hit.text}")
    return "\n\n".join(blocks)


def format_source(index: int, hit: Hit) -> str:
    """e.g. '[S1] hr_leave_policy.pdf, p.1, chunk 0' (the tag lets the UI map it to the answer)."""
    page = f", p.{hit.page}" if hit.page else ""
    return f"[S{index}] {hit.source}{page}, chunk {hit.chunk_index}"


@dataclass
class GenerationResult:
    answer: str
    sources: List[str] = field(default_factory=list)
    gated: bool = False            # True when we refused without calling the LLM (weak retrieval)
    invalid_citations: List[int] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------------------
class GenerationService:
    """Talks to Ollama. The client is created once at startup (see main.py)."""

    def __init__(
        self,
        settings: Settings,
        store_config: Dict[str, Any],
        client: Optional[Any] = None,
        health_client: Optional[Any] = None,
    ):
        prompt_cfg = store_config.get("prompt", {}) or {}
        self.system_prompt: str = prompt_cfg.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.user_template: str = prompt_cfg.get("user_template", DEFAULT_USER_TEMPLATE)
        self.refusal: str = prompt_cfg.get("refusal_sentence", DEFAULT_REFUSAL)

        self.model: str = resolve(settings.ollama_model, store_config, "ollama_model", "llama3.2")
        self.min_similarity: float = float(resolve(settings.min_similarity, store_config, "min_similarity", 0.25))
        self.temperature = settings.temperature
        self.num_ctx = settings.num_ctx

        # One long-timeout client for generation, one short-timeout client for /health.
        self._client = client or ollama.Client(host=settings.ollama_host, timeout=settings.ollama_timeout)
        self._health_client = health_client or ollama.Client(host=settings.ollama_host, timeout=2.0)
        logger.info("Generation ready: model=%s | min_similarity=%.2f | host=%s",
                    self.model, self.min_similarity, settings.ollama_host)

    # ------------------------------------------------------------------ health
    def check_ollama(self) -> Tuple[bool, bool]:
        """Returns (server_reachable, model_is_installed). Never raises."""
        try:
            listed = self._health_client.list()["models"]
        except Exception:
            return False, False
        names = []
        for item in listed:
            try:
                names.append(item["model"])
            except (KeyError, TypeError):
                names.append(item["name"])
        installed = any(n == self.model or n.startswith(self.model + ":") for n in names)
        return True, installed

    # ------------------------------------------------------------------ generation
    def _call_llm(self, question: str, hits: List[Hit]) -> str:
        user_prompt = self.user_template.format(context=build_context(hits), question=question)
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": self.temperature, "num_ctx": self.num_ctx, "seed": 42},
            )
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                raise OllamaUnavailableError(
                    f"Model '{self.model}' is not installed in Ollama. Run: ollama pull {self.model}"
                ) from exc
            raise GenerationError(f"Ollama returned an error ({exc.status_code}): {exc.error}") from exc
        except Exception as exc:  # connection refused, timeout, ...
            raise OllamaUnavailableError(
                "Could not reach the Ollama server. Make sure Ollama is running (ollama serve)."
            ) from exc
        return response["message"]["content"].strip()

    def generate(self, question: str, hits: List[Hit]) -> GenerationResult:
        """Retrieval gate -> LLM -> citation validation."""
        top_similarity = hits[0].similarity if hits else 0.0

        # Similarity gate: nothing relevant retrieved -> refuse WITHOUT calling the LLM
        # (the cheapest and most reliable defence against hallucination on out-of-scope questions).
        if not hits or top_similarity < self.min_similarity:
            logger.info("Gated (top similarity %.3f < %.2f): refusing without LLM call", top_similarity, self.min_similarity)
            return GenerationResult(answer=self.refusal, sources=[], gated=True)

        answer = self._call_llm(question, hits)
        valid, invalid = parse_citations(answer, len(hits))

        if invalid:
            logger.warning("Model cited non-existent excerpt(s): %s", invalid)
        if is_refusal(answer):
            return GenerationResult(answer=answer, sources=[], invalid_citations=invalid)
        if not valid:
            # The answer is not backed by any verifiable citation: do NOT present retrieved chunks as its sources.
            logger.warning("Answer has no valid [S#] citation; returning it without sources.")

        return GenerationResult(
            answer=answer,
            sources=[format_source(i, hits[i - 1]) for i in valid],
            invalid_citations=invalid,
        )
