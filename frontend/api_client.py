"""Thin client for the RAG backend.

The backend URL is NEVER hard-coded: it comes from the API_BASE_URL environment variable
(set in frontend/.env). Every failure is converted into a BackendError carrying a message that
is safe and friendly to show to the user.
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv

FRONTEND_DIR = Path(__file__).resolve().parent
load_dotenv(FRONTEND_DIR / ".env")          # does not override variables already set in the environment

CONNECT_TIMEOUT_SECONDS = 5
HEALTH_TIMEOUT_SECONDS = 3
DEFAULT_READ_TIMEOUT_SECONDS = 150          # above the backend's own LLM timeout (120 s)


class BackendError(Exception):
    """Something went wrong talking to the backend. `user_message` is meant to be shown as-is."""

    def __init__(self, user_message: str, kind: str = "error", status_code: Optional[int] = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.kind = kind                     # config | unreachable | timeout | invalid | unavailable | llm | server | bad_response
        self.status_code = status_code


# ----------------------------------------------------------------------------- data classes
@dataclass(frozen=True)
class Source:
    tag: str        # "S1"  (matches the [S1] tag inside the answer)
    label: str      # "hr_leave_policy.pdf · page 1 · chunk 0"


@dataclass(frozen=True)
class Answer:
    text: str
    sources: List[Source]

    @property
    def refused(self) -> bool:
        """True when the assistant said the documents do not contain the answer."""
        return is_refusal(self.text)


@dataclass(frozen=True)
class Health:
    status: str                              # "ok" | "degraded"
    vector_store_loaded: bool
    ollama_reachable: bool
    model_available: bool
    num_chunks: Optional[int] = None
    embedding_model: Optional[str] = None
    ollama_model: Optional[str] = None
    detail: Optional[str] = None


# ----------------------------------------------------------------------------- helpers
def is_refusal(text: str) -> bool:
    normalized = text.strip().lower().replace("\u2019", "'")
    return normalized.startswith("i don't know")


_SOURCE_RE = re.compile(r"^\[(S\d+)\]\s*(.*)$")


def parse_source(raw: str) -> Source:
    """'[S1] hr_leave_policy.pdf, p.1, chunk 0'  ->  Source('S1', 'hr_leave_policy.pdf · page 1 · chunk 0')."""
    match = _SOURCE_RE.match(raw.strip())
    tag, rest = (match.group(1), match.group(2)) if match else ("", raw.strip())
    parts = [re.sub(r"^p\.(\d+)$", r"page \1", part.strip()) for part in rest.split(",") if part.strip()]
    return Source(tag=tag, label=" \u00b7 ".join(parts) or rest)


def get_base_url(base_url: Optional[str] = None) -> str:
    """The backend URL, from the argument or from API_BASE_URL. Raises a friendly error if it is missing."""
    url = (base_url or os.environ.get("API_BASE_URL", "")).strip().rstrip("/")
    if not url:
        raise BackendError(
            "The backend address is not configured. Set API_BASE_URL in frontend/.env "
            "(for example http://127.0.0.1:8000) and restart the app.",
            kind="config",
        )
    if not url.startswith(("http://", "https://")):
        raise BackendError(f"API_BASE_URL must start with http:// or https:// (currently '{url}').", kind="config")
    return url


def get_read_timeout() -> float:
    try:
        return float(os.environ.get("REQUEST_TIMEOUT_SECONDS", DEFAULT_READ_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_READ_TIMEOUT_SECONDS


def _detail(response: requests.Response) -> str:
    """Extract the human-readable reason from an error response of the backend (FastAPI format)."""
    try:
        body = response.json()
    except ValueError:
        return (response.text or "").strip()[:200]
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):             # validation errors (HTTP 422)
        messages = [str(item.get("msg", "")).removeprefix("Value error, ") for item in detail if isinstance(item, dict)]
        return "; ".join(m for m in messages if m)
    return ""


def _unreachable(url: str) -> BackendError:
    return BackendError(
        f"Cannot reach the backend at {url}. Make sure it is running "
        f"(in the backend folder: python run.py --no-venv) and try again.",
        kind="unreachable",
    )


# ----------------------------------------------------------------------------- public API
def ask(question: str, base_url: Optional[str] = None, timeout: Optional[float] = None) -> Answer:
    """Send a question to POST /query and return the grounded answer with its sources."""
    question = question.strip()
    if not question:
        raise BackendError("Please type a question first.", kind="invalid")
    url = get_base_url(base_url)
    read_timeout = timeout if timeout is not None else get_read_timeout()

    try:
        response = requests.post(
            f"{url}/query", json={"question": question}, timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout)
        )
    except requests.exceptions.ReadTimeout:
        raise BackendError(
            "The answer is taking too long (the language model may still be loading). "
            "Wait a moment and try again.",
            kind="timeout",
        ) from None
    except requests.exceptions.ConnectionError:      # includes connect timeouts
        raise _unreachable(url) from None
    except requests.exceptions.RequestException as exc:
        raise BackendError(f"The request failed: {type(exc).__name__}.", kind="server") from None

    status = response.status_code
    if status == 200:
        return _parse_answer(response)
    detail = _detail(response)
    if status == 422:
        raise BackendError(f"The question was not accepted: {detail or 'please rephrase it.'}", "invalid", status)
    if status == 503:
        raise BackendError(f"The assistant is not ready yet. {detail}".strip(), "unavailable", status)
    if status == 502:
        raise BackendError(f"The language model returned an error. {detail}".strip(), "llm", status)
    raise BackendError(f"The backend returned an unexpected error (HTTP {status}).", "server", status)


def _parse_answer(response: requests.Response) -> Answer:
    try:
        data = response.json()
        text = data["answer"]
        raw_sources = data.get("sources", [])
        if not isinstance(text, str) or not isinstance(raw_sources, list):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BackendError("The backend sent a response in an unexpected format.", kind="bad_response") from None
    return Answer(text=text, sources=[parse_source(str(s)) for s in raw_sources])


def get_health(base_url: Optional[str] = None) -> Health:
    """Call GET /health. Raises BackendError if the backend cannot be reached."""
    url = get_base_url(base_url)
    try:
        response = requests.get(f"{url}/health", timeout=(CONNECT_TIMEOUT_SECONDS, HEALTH_TIMEOUT_SECONDS))
        response.raise_for_status()
        data = response.json()
        return Health(
            status=str(data["status"]),
            vector_store_loaded=bool(data.get("vector_store_loaded")),
            ollama_reachable=bool(data.get("ollama_reachable")),
            model_available=bool(data.get("model_available")),
            num_chunks=data.get("num_chunks"),
            embedding_model=data.get("embedding_model"),
            ollama_model=data.get("ollama_model"),
            detail=data.get("detail"),
        )
    except requests.exceptions.RequestException:
        raise _unreachable(url) from None
    except (ValueError, KeyError, TypeError):
        raise BackendError("The backend sent a response in an unexpected format.", kind="bad_response") from None
