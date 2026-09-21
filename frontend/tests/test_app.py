"""UI tests for app.py using Streamlit's headless AppTest (no browser, no backend, no Ollama)."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import api_client
from api_client import Answer, BackendError, Health, Source

APP = str(Path(__file__).resolve().parents[1] / "app.py")

HEALTH_OK = Health(status="ok", vector_store_loaded=True, ollama_reachable=True, model_available=True,
                   num_chunks=86, embedding_model="all-MiniLM-L6-v2", ollama_model="llama3.2")
LEAVE_ANSWER = Answer("Full-time employees get 21 days of annual leave. [S1]",
                      [Source("S1", "hr_leave_policy.pdf \u00b7 page 1 \u00b7 chunk 0")])
REFUSAL = Answer("I don't know based on the provided documents.", [])


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    """Healthy fake backend by default. Tests replace `calls` / the functions as needed."""
    st.cache_data.clear()                                    # backend_status() is cached between runs
    monkeypatch.setenv("API_BASE_URL", "http://backend.test")
    calls = []

    def fake_ask(question, *args, **kwargs):
        calls.append(question)
        return LEAVE_ANSWER

    monkeypatch.setattr(api_client, "ask", fake_ask)
    monkeypatch.setattr(api_client, "get_health", lambda *a, **k: HEALTH_OK)
    return calls


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=20).run()


def texts(elements):
    return [e.value for e in elements]


def find_button(container, label):
    return next(b for b in container.button if b.label == label)


# ----------------------------------------------------------------------------- page
def test_page_renders_without_errors():
    at = new_app()
    assert not at.exception
    assert "Helios Document Assistant" in at.title[0].value
    assert any("Backend ready" in v for v in texts(at.sidebar.success))
    assert len(at.chat_message) == 0


def test_backend_status_is_shown_in_the_sidebar(monkeypatch):
    degraded = Health(status="degraded", vector_store_loaded=True, ollama_reachable=False,
                      model_available=False, detail="Ollama is not reachable.")
    monkeypatch.setattr(api_client, "get_health", lambda *a, **k: degraded)
    at = new_app()
    assert any("Ollama is not reachable" in v for v in texts(at.sidebar.warning))

    st.cache_data.clear()

    def down(*a, **k):
        raise BackendError("Cannot reach the backend at http://backend.test.", kind="unreachable")

    monkeypatch.setattr(api_client, "get_health", down)
    at = new_app()
    assert any("Cannot reach the backend" in v for v in texts(at.sidebar.error))
    assert not at.exception


# ----------------------------------------------------------------------------- asking questions
def test_question_shows_answer_and_cited_sources(backend):
    at = new_app()
    at.chat_input[0].set_value("How many days of annual leave?").run()
    assert not at.exception
    assert backend == ["How many days of annual leave?"]
    assert len(at.chat_message) == 2
    page_text = "\n".join(texts(at.markdown))
    assert "21 days of annual leave" in page_text
    assert "**Sources**" in page_text and "hr_leave_policy.pdf" in page_text and "[S1]" in page_text


def test_refusal_is_explained_and_has_no_sources(monkeypatch):
    monkeypatch.setattr(api_client, "ask", lambda q, *a, **k: REFUSAL)
    at = new_app()
    at.chat_input[0].set_value("What is the CEO's salary?").run()
    assert any("do not contain this information" in v for v in texts(at.info))
    assert "**Sources**" not in "\n".join(texts(at.markdown))


def test_backend_error_is_shown_as_a_friendly_message(monkeypatch):
    def failing(*a, **k):
        raise BackendError("Cannot reach the backend at http://backend.test. Make sure it is running.", kind="unreachable")

    monkeypatch.setattr(api_client, "ask", failing)
    at = new_app()
    at.chat_input[0].set_value("hello?").run()
    assert not at.exception                                   # the app must never crash
    assert any("Cannot reach the backend" in v for v in texts(at.error))
    assert len(at.chat_message) == 2                          # the question and the error stay in the conversation


def test_conversation_keeps_previous_turns(backend):
    at = new_app()
    at.chat_input[0].set_value("first question").run()
    at.chat_input[0].set_value("second question").run()
    assert backend == ["first question", "second question"]
    assert len(at.chat_message) == 4


def test_dollar_signs_are_escaped_so_prices_are_not_rendered_as_math(monkeypatch):
    monkeypatch.setattr(api_client, "ask", lambda q, *a, **k: Answer("The cap is $260, or $180 elsewhere. [S1]", []))
    at = new_app()
    at.chat_input[0].set_value("hotel?").run()
    page_text = "\n".join(texts(at.markdown))
    assert "\\$260" in page_text and "\\$180" in page_text


# ----------------------------------------------------------------------------- sidebar buttons
def test_example_button_asks_that_question(backend):
    at = new_app()
    find_button(at.sidebar, "Annual leave").click().run()
    assert not at.exception
    assert backend == ["How many days of annual leave do full-time employees get per year?"]
    assert len(at.chat_message) == 2


def test_clear_conversation_empties_the_chat(backend):
    at = new_app()
    at.chat_input[0].set_value("question").run()
    assert len(at.chat_message) == 2
    find_button(at.sidebar, "Clear conversation").click().run()
    assert len(at.chat_message) == 0


def test_missing_configuration_is_reported_not_a_crash(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.undo()                                        # restore real api_client.ask / get_health
    monkeypatch.delenv("API_BASE_URL", raising=False)
    st.cache_data.clear()
    at = new_app()
    assert not at.exception
    assert any("API_BASE_URL" in v for v in texts(at.sidebar.error))
    at.chat_input[0].set_value("hello").run()
    assert not at.exception and any("API_BASE_URL" in v for v in texts(at.error))
