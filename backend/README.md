# Backend (FastAPI)

Serves the RAG pipeline built in `rag_pipeline.ipynb`. `POST /query` retrieves the most relevant chunks from the persisted ChromaDB store, asks a local Ollama model to answer **only** from them, and returns the answer with its cited sources.

## Project layout
```
Final Project/
├── rag_pipeline.ipynb            # notebook (exports the vector store)
├── data/
│   ├── documents/                # source documents
│   └── vector_store/             # config.json + chroma/   <- written by the notebook (section 2.7)
├── docs/
└── backend/                      # this folder
    ├── app/                      # FastAPI application
    ├── tests/
    ├── run.py                    # one-command launcher (start the API / run the tests)
    ├── .env                      # ready-to-use local settings (not committed)
    ├── .env.example
    ├── requirements.txt
    └── Dockerfile
```
The backend **finds the vector store by itself**: it looks in `backend/data/vector_store/` and in `<project>/data/vector_store/` and uses the most recently built one. `GET /health` shows which folder is being served.

## Run
1. Make sure Ollama is running and the model is installed: `ollama pull llama3.2`
2. From the `backend/` folder:
   ```powershell
   python run.py
   ```
   `run.py` creates `.venv`, installs `requirements.txt` (the first run takes a few minutes; later runs are quick), checks that everything is ready and starts the API. **If you already have all the packages installed in your current Python** (e.g. the one you used for the notebook), use `python run.py --no-venv` to skip the virtual environment.
3. Read the **Preflight** lines it prints. They tell you whether `/health` will say `ok`: vector store found, Ollama reachable with the model installed, port free.
4. Open http://127.0.0.1:8000/health (should show `"status": "ok"`), then http://127.0.0.1:8000/docs to try `/query`.

| Command | What it does |
|---|---|
| `python run.py` | Start the API on port 8000 (creates `.venv` if needed) |
| `python run.py --no-venv` | Start using the current Python (packages must already be installed) |
| `python run.py --test` | Run the test-suite |
| `python run.py --port 8001` | Use another port (e.g. if 8000 is taken) |
| `python run.py --reload` | Auto-restart on code changes (development) |
| `python run.py --skip-install` | Do not run pip (faster start once everything is installed) |

After re-running the notebook (a new vector store), **restart the server**: the store is loaded once at startup.

Manual alternative (without `run.py`):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

## Endpoints
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Always 200. `status` is `ok` or `degraded` (vector store not loaded, Ollama down, model not pulled) with a `detail` message. Also shows the vector store folder, chunk count and embedding model. |
| POST | `/query` | Body `{"question": "..."}` returns `{"answer": "...", "sources": ["[S1] file.pdf, p.1, chunk 0"]}` |

`/query` status codes: **200** ok, **422** invalid input (empty, whitespace-only, missing, too long), **503** Ollama unreachable / model not pulled / vector store not loaded, **502** Ollama returned an error.

```bash
curl -X POST http://127.0.0.1:8000/query -H "Content-Type: application/json" \
     -d '{"question": "How many days of annual leave do full-time employees get per year?"}'
```

## Configuration (`.env`)
See `.env.example`. Nothing needs to be edited for the layout above. Retrieval settings (`top_k`, `min_similarity`), the model name and the prompt templates default to what the notebook saved in `config.json`; set `OLLAMA_MODEL`, `TOP_K`, `MIN_SIMILARITY` or `VECTOR_STORE_DIR` only to override them.

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server (`127.0.0.1` avoids the Windows IPv6 `localhost` problem) |
| `OLLAMA_TIMEOUT` | `120` | Seconds to wait for the LLM |
| `TEMPERATURE` / `NUM_CTX` | `0.0` / `4096` | LLM generation settings |
| `CORS_ORIGINS` | Streamlit (8501) and Gradio (7860) on localhost | Frontend origins allowed to call the API |
| `LOG_LEVEL` | `INFO` | Logging level |
| `VECTOR_STORE_DIR` | *(auto-detected)* | Force a specific vector store folder |
| `OLLAMA_MODEL`, `TOP_K`, `MIN_SIMILARITY` | *(from `config.json`)* | Optional overrides |

## Tests
`python run.py --test`, or `pytest` inside `backend/`. The tests use fake services, so they need neither Ollama nor the vector store.

## Docker
The image must contain the vector store, so copy it into the backend folder first (from the project root):
```powershell
xcopy /E /I data\vector_store backend\data\vector_store
cd backend
docker build -t rag-backend .
docker run -p 8000:8000 rag-backend
```
Ollama runs on the host machine, not in the container (`OLLAMA_HOST` defaults to `http://host.docker.internal:11434` inside the image). On Linux add `--add-host=host.docker.internal:host-gateway`.

## Important
`chromadb` in `requirements.txt` must be the same version that built the store in the notebook, otherwise the store may not open.
