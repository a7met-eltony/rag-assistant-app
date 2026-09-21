"""API tests. They use fake services, so they run in milliseconds and need neither Ollama nor a vector store."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.generation import GenerationError, GenerationResult, OllamaUnavailableError
from app.services.retrieval import Hit


# ----------------------------------------------------------------------------- fakes
class FakeRetrieval:
    num_chunks = 86
    embedding_model = "sentence-transformers/all-MiniLM-L6-v2"

    def retrieve(self, question, top_k=None):
        return [Hit(rank=1, chunk_id="hr_leave_policy.pdf::p1::chunk000", text="Full-time employees ... 21 days ...",
                    source="hr_leave_policy.pdf", page=1, chunk_index=0, similarity=0.71)]


class FakeGeneration:
    model = "llama3.2"

    def __init__(self, error=None, reachable=True, installed=True):
        self.error = error
        self._status = (reachable, installed)

    def check_ollama(self):
        return self._status

    def generate(self, question, hits):
        if self.error:
            raise self.error
        return GenerationResult(
            answer="Full-time employees get 21 days of annual leave per year. [S1]",
            sources=["[S1] hr_leave_policy.pdf, p.1, chunk 0"],
        )


@pytest.fixture
def client():
    """TestClient WITHOUT the 'with' block: the lifespan (real store + model) is not started."""
    app.state.retrieval = FakeRetrieval()
    app.state.generation = FakeGeneration()
    app.state.startup_error = None
    yield TestClient(app)
    app.state.retrieval = None
    app.state.generation = None


# ----------------------------------------------------------------------------- /health
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["vector_store_loaded"] is True
    assert body["num_chunks"] == 86
    assert body["model_available"] is True


def test_health_degraded_when_ollama_is_down(client):
    app.state.generation = FakeGeneration(reachable=False, installed=False)
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["ollama_reachable"] is False
    assert "Ollama" in body["detail"]


def test_health_degraded_when_store_not_loaded(client):
    app.state.retrieval = None
    app.state.startup_error = "Vector store not found in data/vector_store."
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["vector_store_loaded"] is False
    assert "Vector store not found" in body["detail"]


# ----------------------------------------------------------------------------- /query: happy path
def test_query_happy_path(client):
    response = client.post("/query", json={"question": "How many days of annual leave do I get?"})
    assert response.status_code == 200
    body = response.json()
    assert "21 days" in body["answer"]
    assert body["sources"] == ["[S1] hr_leave_policy.pdf, p.1, chunk 0"]


def test_query_strips_whitespace_around_question(client):
    response = client.post("/query", json={"question": "   annual leave?   "})
    assert response.status_code == 200


# ----------------------------------------------------------------------------- /query: invalid input -> 422
@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},                 # empty
        {"question": "     "},            # whitespace only
        {},                               # missing field
        {"question": 123},                # wrong type
        {"question": "x" * 1001},         # too long
    ],
)
def test_query_invalid_input_returns_422(client, payload):
    response = client.post("/query", json=payload)
    assert response.status_code == 422


# ----------------------------------------------------------------------------- /query: service failures
def test_query_returns_503_when_ollama_is_down(client):
    app.state.generation = FakeGeneration(error=OllamaUnavailableError("Could not reach the Ollama server."))
    response = client.post("/query", json={"question": "anything"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


def test_query_returns_502_on_generation_error(client):
    app.state.generation = FakeGeneration(error=GenerationError("Ollama returned an error (500)"))
    response = client.post("/query", json={"question": "anything"})
    assert response.status_code == 502


def test_query_returns_503_when_vector_store_not_loaded(client):
    app.state.retrieval = None
    app.state.startup_error = "Vector store not found."
    response = client.post("/query", json={"question": "anything"})
    assert response.status_code == 503
    assert "Vector store" in response.json()["detail"]
