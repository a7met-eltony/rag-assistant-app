"""Tests for finding the vector store automatically (no manual path editing) and for loading the embedder."""
import os
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import Settings
from app.main import app
from app.services import retrieval
from app.services.retrieval import RetrievalService, VectorStoreError


def make_store(path, mtime=None):
    """Create a folder that looks like the notebook's export (config.json + chroma/)."""
    (path / "chroma").mkdir(parents=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    if mtime is not None:
        os.utime(path / "config.json", (mtime, mtime))
    return path


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fake project:   <tmp>/backend  and  <tmp>/data/vector_store  (the layout of 'Final Project')."""
    backend = tmp_path / "backend"
    backend.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", backend)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    return tmp_path


# ----------------------------------------------------------------------------- auto-detection
def test_finds_store_written_by_the_notebook_in_the_project_root(project):
    store = make_store(project / "data" / "vector_store")
    assert Settings(_env_file=None).resolve_vector_store() == store


def test_finds_store_inside_backend_folder(project):
    store = make_store(project / "backend" / "data" / "vector_store")
    assert Settings(_env_file=None).resolve_vector_store() == store


def test_newest_store_wins_when_both_exist(project):
    old = make_store(project / "backend" / "data" / "vector_store", mtime=1_000_000)
    new = make_store(project / "data" / "vector_store", mtime=2_000_000)
    assert Settings(_env_file=None).resolve_vector_store() == new
    os.utime(old / "config.json", (3_000_000, 3_000_000))          # now the backend copy is the newer one
    assert Settings(_env_file=None).resolve_vector_store() == old


def test_explicit_vector_store_dir_wins_over_auto_detection(project):
    make_store(project / "data" / "vector_store")
    custom = make_store(project / "somewhere" / "else")
    assert Settings(_env_file=None, vector_store_dir=str(custom)).resolve_vector_store() == custom


def test_incomplete_folder_is_ignored(project):
    (project / "data" / "vector_store").mkdir(parents=True)          # no config.json / chroma/
    assert Settings(_env_file=None).resolve_vector_store() is None


def test_missing_store_gives_a_helpful_error_listing_searched_folders(project):
    with pytest.raises(VectorStoreError) as excinfo:
        RetrievalService.load(Settings(_env_file=None))
    message = str(excinfo.value)
    assert "Vector store not found" in message
    assert "vector_store" in message and "notebook" in message


# ----------------------------------------------------------------------------- embedder loading
def test_embedder_prefers_local_cache(monkeypatch):
    calls = []

    class Stub:
        def __init__(self, name, **kwargs):
            calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=Stub))
    retrieval.load_embedder("some/model")
    assert calls == [{"local_files_only": True}]


def test_embedder_downloads_when_not_cached(monkeypatch):
    calls = []

    class Stub:
        def __init__(self, name, **kwargs):
            calls.append(kwargs)
            if kwargs.get("local_files_only"):
                raise OSError("not cached")

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=Stub))
    retrieval.load_embedder("some/model")
    assert calls == [{"local_files_only": True}, {}]


# ----------------------------------------------------------------------------- /health shows which store is served
def test_health_reports_the_store_folder():
    class FakeRetrieval:
        num_chunks = 86
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        store_dir = "D:/Final Project/data/vector_store"

    class FakeGeneration:
        model = "llama3.2"

        def check_ollama(self):
            return True, True

    app.state.retrieval, app.state.generation, app.state.startup_error = FakeRetrieval(), FakeGeneration(), None
    try:
        body = TestClient(app).get("/health").json()
    finally:
        app.state.retrieval = app.state.generation = None
    assert body["status"] == "ok"
    assert body["vector_store_dir"].endswith("data/vector_store")
