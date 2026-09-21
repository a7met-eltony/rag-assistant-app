# Frontend (Streamlit)

Chat interface for the RAG backend: type a question, get an answer generated **only** from the indexed documents, with the sources it cites.

## Project layout
```
Final Project/
├── rag_pipeline.ipynb
├── data/                  # documents + vector store (written by the notebook)
├── backend/               # FastAPI API   (port 8000)
└── frontend/              # this folder   (port 8501)
    ├── app.py             # the Streamlit app
    ├── api_client.py      # wrapper around the backend API (all error handling lives here)
    ├── run.py             # one-command launcher
    ├── .env               # API_BASE_URL=http://127.0.0.1:8000   (not committed)
    ├── .env.example
    ├── .streamlit/config.toml
    ├── requirements.txt
    └── tests/
```

## Run
The **backend must be running first** (see `backend/README.md`): in one terminal, `cd backend` then `python run.py --no-venv`, wait for `Application startup complete`.

In a second terminal:
```powershell
cd frontend
python run.py
```
The launcher checks that the backend is ready, starts the app and opens http://127.0.0.1:8501 in your browser.

- If `streamlit` is not installed in your Python, `run.py` creates `frontend/.venv` and installs `requirements.txt` there automatically (first time: a few minutes).
- If you prefer to install into your current Python: `pip install -r requirements.txt`, then `python run.py --no-venv`.

| Command | What it does |
|---|---|
| `python run.py` | Start the app on port 8501 and open the browser |
| `python run.py --no-browser` | Start without opening the browser |
| `python run.py --port 8502` | Use another port |
| `python run.py --venv` | Always use an isolated `.venv` |
| `python run.py --no-venv` | Never create a `.venv`; use the current Python |
| `python run.py --test` | Run the tests |

Without the launcher: `streamlit run app.py`.

## What the app does
- **Chat interface:** question box at the bottom, conversation history above it.
- **Grounded answers with citations:** the answer contains `[S1]`-style tags and a **Sources** list below it (file, page, chunk) so every claim can be traced to a document.
- **Refusals are explained:** when the documents do not contain the answer, the app says so instead of showing an empty answer.
- **Loading state:** a spinner while the backend retrieves passages and the local model writes the answer.
- **Friendly errors:** backend not running, model still loading (timeout), invalid question, backend not ready. The app never shows a stack trace.
- **Sidebar:** live backend status, example questions (one of them is deliberately *not* in the documents), "Refresh status" and "Clear conversation".

## Configuration (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `API_BASE_URL` | `http://127.0.0.1:8000` | Backend address. **Read from the environment: it is never hard-coded.** |
| `REQUEST_TIMEOUT_SECONDS` | `150` | How long to wait for an answer (keep above the backend's `OLLAMA_TIMEOUT`, 120) |

## Tests
`python run.py --test` (or `pytest` inside `frontend/`). They need neither the backend nor Ollama:
- `tests/test_api_client.py` talks to a real local HTTP server: success, 422/502/503/500 responses, malformed replies, timeouts, connection refused, missing configuration, and a check that no URL is hard-coded.
- `tests/test_app.py` drives the real UI headlessly (Streamlit `AppTest`): answers with sources, refusals, errors, example buttons, clearing the chat.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Cannot reach the backend..." | Start the backend (`cd backend`, `python run.py --no-venv`) and click **Refresh status** |
| Sidebar says "not ready" | Follow the reason shown (Ollama not running, model not pulled, vector store missing) |
| "The answer is taking too long" | The local model may be loading the first time; wait a moment and ask again |
| Port 8501 in use | Another copy is running: close it or use `--port 8502` |
