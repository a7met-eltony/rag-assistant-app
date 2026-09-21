"""Unit tests for the service layer (retrieval mapping, citations, similarity gate, Ollama errors)."""
import numpy as np
import ollama
import pytest

from app.core.config import Settings, resolve
from app.services.generation import (
    GenerationError,
    GenerationService,
    OllamaUnavailableError,
    build_context,
    format_source,
    is_refusal,
    parse_citations,
)
from app.services.retrieval import Hit, RetrievalService


def make_hit(rank=1, source="hr_leave_policy.pdf", page=1, chunk_index=0, similarity=0.7):
    return Hit(rank=rank, chunk_id=f"{source}::{rank}", text="Some text.", source=source,
               page=page, chunk_index=chunk_index, similarity=similarity)


# ----------------------------------------------------------------------------- helpers
def test_parse_citations_valid_and_invalid():
    assert parse_citations("Answer [S1] and more [S3].", n_hits=3) == ([1, 3], [])
    assert parse_citations("Bad [S9].", n_hits=3) == ([], [9])
    assert parse_citations("Combined [S1, S2].", n_hits=3) == ([1, 2], [])
    assert parse_citations("No tags here.", n_hits=3) == ([], [])


def test_is_refusal():
    assert is_refusal("I don't know based on the provided documents.")
    assert is_refusal("I don’t know based on the provided documents.")   # curly apostrophe
    assert not is_refusal("Employees get 21 days of leave. [S1]")


def test_build_context_and_format_source():
    hits = [make_hit(1, "a.pdf", page=2), make_hit(2, "b.txt", page=0, chunk_index=3)]
    context = build_context(hits)
    assert "[S1] (source: a.pdf, page 2)" in context
    assert "[S2] (source: b.txt)" in context           # no page for plain-text files
    assert format_source(1, hits[0]) == "[S1] a.pdf, p.2, chunk 0"
    assert format_source(2, hits[1]) == "[S2] b.txt, chunk 3"


def test_settings_helpers():
    settings = Settings(_env_file=None, cors_origins="http://a.com, http://b.com ,")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]
    assert resolve(None, {"top_k": 7}, "top_k", 5) == 7        # from the notebook's config.json
    assert resolve(3, {"top_k": 7}, "top_k", 5) == 3           # explicit setting wins
    assert resolve(None, {}, "top_k", 5) == 5                  # built-in default


# ----------------------------------------------------------------------------- retrieval mapping
class FakeCollection:
    def count(self):
        return 2

    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [["c1", "c2"]],
            "documents": [["text one", "text two"]],
            "metadatas": [[{"source": "a.pdf", "page": 3, "chunk_index": 1},
                           {"source": "b.md", "page": 0, "chunk_index": 0}]],
            "distances": [[0.25, 0.9]],
        }


class FakeEmbedder:
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        return np.zeros((len(texts), 4))


def test_retrieve_converts_distance_to_similarity_and_maps_metadata():
    service = RetrievalService(FakeCollection(), FakeEmbedder(), {"embedding_model": "m"}, top_k=2)
    hits = service.retrieve("question")
    assert [h.source for h in hits] == ["a.pdf", "b.md"]
    assert hits[0].similarity == pytest.approx(0.75)           # 1 - cosine distance
    assert hits[0].page == 3 and hits[1].page == 0
    assert service.num_chunks == 2 and service.embedding_model == "m"


# ----------------------------------------------------------------------------- generation
class FakeOllamaClient:
    """Stands in for ollama.Client. Records calls so tests can assert the LLM was (not) used."""

    def __init__(self, content="Answer. [S1]", error=None):
        self.content, self.error, self.calls = content, error, 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return {"message": {"content": self.content}}

    def list(self):
        return {"models": [{"model": "llama3.2:latest"}]}


def make_service(client, **store_overrides):
    store_config = {"ollama_model": "llama3.2", "min_similarity": 0.25, **store_overrides}
    return GenerationService(Settings(_env_file=None), store_config, client=client, health_client=client)


def test_generate_uses_llm_and_returns_validated_sources():
    client = FakeOllamaClient("Employees get 21 days. [S2]")
    result = make_service(client).generate("q", [make_hit(1, "a.pdf"), make_hit(2, "b.pdf", page=0, chunk_index=4)])
    assert result.answer == "Employees get 21 days. [S2]"
    assert result.sources == ["[S2] b.pdf, chunk 4"]           # only the cited chunk, tagged with its number
    assert client.calls == 1


def test_similarity_gate_refuses_without_calling_llm():
    client = FakeOllamaClient()
    result = make_service(client).generate("q", [make_hit(similarity=0.05)])
    assert result.gated is True
    assert result.sources == []
    assert "don't know" in result.answer.lower()
    assert client.calls == 0                                   # the LLM was never called


def test_refusal_from_model_has_no_sources():
    client = FakeOllamaClient("I don't know based on the provided documents.")
    result = make_service(client).generate("q", [make_hit()])
    assert result.sources == []


def test_answer_without_valid_citation_is_not_given_fake_sources():
    client = FakeOllamaClient("Employees get 21 days.")        # no [S#] tag
    result = make_service(client).generate("q", [make_hit()])
    assert result.answer == "Employees get 21 days."
    assert result.sources == []                                # retrieved chunks are NOT presented as its sources


def test_invalid_citation_is_reported_and_not_returned():
    client = FakeOllamaClient("Employees get 21 days. [S7]")
    result = make_service(client).generate("q", [make_hit()])
    assert result.invalid_citations == [7]
    assert result.sources == []


def test_missing_model_maps_to_unavailable_error():
    client = FakeOllamaClient(error=ollama.ResponseError("model not found", 404))
    with pytest.raises(OllamaUnavailableError, match="ollama pull"):
        make_service(client).generate("q", [make_hit()])


def test_connection_error_maps_to_unavailable_error():
    client = FakeOllamaClient(error=ConnectionError("refused"))
    with pytest.raises(OllamaUnavailableError, match="Ollama"):
        make_service(client).generate("q", [make_hit()])


def test_other_ollama_errors_map_to_generation_error():
    client = FakeOllamaClient(error=ollama.ResponseError("boom", 500))
    with pytest.raises(GenerationError) as excinfo:
        make_service(client).generate("q", [make_hit()])
    assert not isinstance(excinfo.value, OllamaUnavailableError)


def test_check_ollama_reports_installed_model():
    assert make_service(FakeOllamaClient()).check_ollama() == (True, True)
    assert make_service(FakeOllamaClient(), ollama_model="mistral").check_ollama() == (True, False)
