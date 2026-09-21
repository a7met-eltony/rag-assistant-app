"""Tests for api_client. They talk to a REAL local HTTP server, so timeouts and connection errors are genuine."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import api_client
from api_client import BackendError

ANSWER_OK = {"answer": "Full-time employees get 21 days. [S1]", "sources": ["[S1] hr_leave_policy.pdf, p.1, chunk 0"]}
HEALTH_OK = {"status": "ok", "vector_store_loaded": True, "num_chunks": 86, "embedding_model": "m",
             "ollama_reachable": True, "ollama_model": "llama3.2", "model_available": True, "detail": None}


class FakeBackend:
    """A tiny HTTP server whose responses are configured per test: routes[(method, path)] = (status, body, delay)."""

    def __init__(self):
        self.routes, self.requests = {}, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _respond(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append((self.command, self.path, self.rfile.read(length) if length else b""))
                status, payload, delay = outer.routes.get((self.command, self.path), (404, {"detail": "not found"}, 0))
                time.sleep(delay)
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = do_POST = _respond

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setenv("API_BASE_URL", fake.url)
    yield fake
    fake.stop()


# ----------------------------------------------------------------------------- ask(): success
def test_ask_returns_answer_and_parsed_sources(backend):
    backend.routes[("POST", "/query")] = (200, ANSWER_OK, 0)
    answer = api_client.ask("  How many days of annual leave?  ")
    assert answer.text.startswith("Full-time employees get 21 days")
    assert [(s.tag, s.label) for s in answer.sources] == [("S1", "hr_leave_policy.pdf \u00b7 page 1 \u00b7 chunk 0")]
    assert not answer.refused
    # the question is sent trimmed, as JSON
    method, path, body = backend.requests[-1]
    assert (method, path, json.loads(body)) == ("POST", "/query", {"question": "How many days of annual leave?"})


def test_refusal_is_detected_and_has_no_sources(backend):
    backend.routes[("POST", "/query")] = (200, {"answer": "I don't know based on the provided documents.", "sources": []}, 0)
    answer = api_client.ask("What is the CEO's salary?")
    assert answer.refused and answer.sources == []


def test_refusal_detection_handles_curly_apostrophe():
    assert api_client.is_refusal("I don\u2019t know based on the provided documents.")
    assert not api_client.is_refusal("The limit is $260. [S1]")


# ----------------------------------------------------------------------------- ask(): errors are friendly
def test_blank_question_is_rejected_without_any_request(backend):
    with pytest.raises(BackendError) as info:
        api_client.ask("   ")
    assert info.value.kind == "invalid" and backend.requests == []


def test_422_message_contains_the_reason(backend):
    detail = [{"type": "value_error", "loc": ["body", "question"], "msg": "Value error, question must not be empty or whitespace"}]
    backend.routes[("POST", "/query")] = (422, {"detail": detail}, 0)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "invalid" and info.value.status_code == 422
    assert "question must not be empty" in info.value.user_message


def test_503_becomes_a_not_ready_message_with_the_backend_reason(backend):
    backend.routes[("POST", "/query")] = (503, {"detail": "Could not reach the Ollama server."}, 0)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "unavailable" and "Ollama" in info.value.user_message


def test_502_is_reported_as_a_language_model_error(backend):
    backend.routes[("POST", "/query")] = (502, {"detail": "model failed"}, 0)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "llm" and "model failed" in info.value.user_message


def test_unexpected_500_hides_technical_details(backend):
    backend.routes[("POST", "/query")] = (500, b"Traceback (most recent call last): secret internals", 0)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "server" and "Traceback" not in info.value.user_message


@pytest.mark.parametrize("body", [b"not json at all", b'{"unexpected": true}', b'{"answer": 5, "sources": []}'])
def test_malformed_success_response_is_a_bad_response_error(backend, body):
    backend.routes[("POST", "/query")] = (200, body, 0)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "bad_response"


def test_unreachable_backend_says_how_to_start_it(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]                    # nothing listens here after the socket closes
    monkeypatch.setenv("API_BASE_URL", f"http://127.0.0.1:{free_port}")
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "unreachable"
    assert f"127.0.0.1:{free_port}" in info.value.user_message and "run.py" in info.value.user_message


def test_slow_backend_times_out_with_a_friendly_message(backend):
    backend.routes[("POST", "/query")] = (200, ANSWER_OK, 1.5)
    with pytest.raises(BackendError) as info:
        api_client.ask("x", timeout=0.3)
    assert info.value.kind == "timeout" and "too long" in info.value.user_message


# ----------------------------------------------------------------------------- configuration
def test_missing_api_base_url_is_a_config_error(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    with pytest.raises(BackendError) as info:
        api_client.ask("x")
    assert info.value.kind == "config" and "API_BASE_URL" in info.value.user_message


def test_base_url_without_scheme_is_a_config_error(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "127.0.0.1:8000")
    with pytest.raises(BackendError) as info:
        api_client.get_base_url()
    assert info.value.kind == "config"


def test_trailing_slash_is_removed(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://127.0.0.1:8000/")
    assert api_client.get_base_url() == "http://127.0.0.1:8000"


def test_read_timeout_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "42")
    assert api_client.get_read_timeout() == 42
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "banana")
    assert api_client.get_read_timeout() == api_client.DEFAULT_READ_TIMEOUT_SECONDS


def test_no_hard_coded_backend_address_in_the_code():
    """Assignment rule: never hard-code the backend URL in the frontend code."""
    import re
    from pathlib import Path

    folder = Path(api_client.__file__).parent
    client_code = (folder / "api_client.py").read_text(encoding="utf-8")
    app_code = (folder / "app.py").read_text(encoding="utf-8")
    # requests must be called with a variable, never with a literal URL
    assert re.search(r"requests\.(get|post)\(\s*f?[\"']https?://", client_code) is None
    # the UI code must not contain any URL at all
    assert "http://" not in app_code and "https://" not in app_code


# ----------------------------------------------------------------------------- health + source parsing
def test_health_is_parsed(backend):
    backend.routes[("GET", "/health")] = (200, HEALTH_OK, 0)
    health = api_client.get_health()
    assert health.status == "ok" and health.num_chunks == 86 and health.ollama_model == "llama3.2"


def test_health_of_a_down_backend_raises_unreachable(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("API_BASE_URL", f"http://127.0.0.1:{port}")
    with pytest.raises(BackendError) as info:
        api_client.get_health()
    assert info.value.kind == "unreachable"


@pytest.mark.parametrize("raw, tag, label", [
    ("[S2] expense_policy.pdf, p.3, chunk 4", "S2", "expense_policy.pdf \u00b7 page 3 \u00b7 chunk 4"),
    ("[S1] onboarding_guide.txt, chunk 0", "S1", "onboarding_guide.txt \u00b7 chunk 0"),
    ("some plain text", "", "some plain text"),
])
def test_parse_source(raw, tag, label):
    source = api_client.parse_source(raw)
    assert (source.tag, source.label) == (tag, label)
