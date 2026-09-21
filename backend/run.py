"""Start the backend with one command:

    python run.py              # from the backend/ folder (or:  python backend/run.py  from anywhere)

What it does
  1. Creates backend/.venv and installs requirements.txt on the first run (later runs skip this quickly).
  2. Runs a preflight check and tells you whether /health will say "ok": vector store found? Ollama
     reachable with the model installed? Port free? It only warns, so the server still starts.
  3. Starts the API on http://127.0.0.1:8000  (Swagger UI: /docs, health: /health).

Options
  --port 8001       use another port          --host 0.0.0.0   listen on all interfaces
  --reload          auto-restart on code changes (development)
  --test            run the test-suite instead of starting the server
  --no-venv         use the current Python instead of .venv (packages must already be installed)
  --skip-install    do not run pip (faster start once everything is installed)

Uses only the Python standard library until the virtual environment is ready.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
VENV_DIR = BACKEND / ".venv"
IN_VENV_FLAG = "RAG_BACKEND_IN_VENV"          # set when we re-launch ourselves inside the venv


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ----------------------------------------------------------------------------- 1) virtual environment
def ensure_venv(skip_install: bool) -> None:
    if not venv_python().exists():
        print("[setup] Creating virtual environment in .venv ...")
        venv.create(VENV_DIR, with_pip=True)
    if skip_install:
        return
    print("[setup] Checking packages (the first run downloads several packages and can take a few minutes) ...")
    try:
        subprocess.check_call([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.txt")])
    except subprocess.CalledProcessError:
        sys.exit("\n[error] Installing the packages failed. Read the messages above (internet connection? disk space?), "
                 "then run the script again.")


def relaunch_inside_venv() -> int:
    """Run this same script again with the venv's Python, so it sees the installed packages."""
    env = dict(os.environ, **{IN_VENV_FLAG: "1"})
    try:
        return subprocess.call([str(venv_python()), str(Path(__file__).resolve()), *sys.argv[1:]], env=env, cwd=BACKEND)
    except KeyboardInterrupt:
        return 0


# ----------------------------------------------------------------------------- 2) preflight
def port_in_use(host: str, port: int) -> bool:
    check_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((check_host, port)) == 0


def installed_ollama_models(host: str) -> list:
    with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=3) as response:
        data = json.load(response)
    return [m.get("model") or m.get("name") or "" for m in data.get("models", [])]


def preflight(host: str, port: int) -> bool:
    """Print what /health will report. Returns False if the port is taken (the server cannot start)."""
    sys.path.insert(0, str(BACKEND))
    from app.core.config import get_settings

    settings = get_settings()
    problems = []
    print("\n=== Preflight ===")

    # Vector store (exported by the notebook)
    store = settings.resolve_vector_store()
    store_cfg = {}
    if store is None:
        searched = ", ".join(str(p) for p in settings.vector_store_candidates)
        print(f"[FAIL] Vector store not found. Looked in: {searched}")
        problems.append("vector store")
    else:
        store_cfg = json.loads((store / "config.json").read_text(encoding="utf-8"))
        print(f"[ OK ] Vector store: {store}  ({store_cfg.get('num_chunks', '?')} chunks, "
              f"{store_cfg.get('embedding_model', '?')})")

    # Ollama + model
    model = settings.ollama_model or store_cfg.get("ollama_model") or "llama3.2"
    try:
        names = installed_ollama_models(settings.ollama_host)
        if any(n == model or n.startswith(model + ":") for n in names):
            print(f"[ OK ] Ollama reachable at {settings.ollama_host}, model '{model}' installed")
        else:
            print(f"[WARN] Ollama is running but model '{model}' is not installed. Run: ollama pull {model}")
            problems.append("model")
    except Exception:
        print(f"[WARN] Ollama is not reachable at {settings.ollama_host}. Start Ollama (or run: ollama serve)")
        problems.append("ollama")

    # Port
    if port_in_use(host, port):
        print(f"[FAIL] Port {port} is already in use (is another backend still running?). "
              f"Close it, or start with:  python run.py --port {port + 1}")
        return False
    print(f"[ OK ] Port {port} is free")

    if problems:
        print(f"\n-> /health will say \"degraded\" until you fix: {', '.join(problems)}. "
              f"The server starts anyway; restart it after the vector store is created.")
    else:
        print("\n-> Everything looks ready: /health should say \"ok\".")
    return True


# ----------------------------------------------------------------------------- 3) start
def main() -> int:
    parser = argparse.ArgumentParser(description="Start the RAG backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-restart on code changes")
    parser.add_argument("--test", action="store_true", help="run the tests instead of the server")
    parser.add_argument("--no-venv", action="store_true", help="use the current Python, not .venv")
    parser.add_argument("--skip-install", action="store_true", help="do not run pip")
    args = parser.parse_args()

    os.chdir(BACKEND)

    # Step 1: make sure we are running inside the project's virtual environment.
    if not args.no_venv and os.environ.get(IN_VENV_FLAG) != "1":
        ensure_venv(args.skip_install)
        return relaunch_inside_venv()

    if args.test:
        import pytest
        return int(pytest.main(["-q"]))

    # Step 2: preflight (warnings only, except a busy port).
    if not preflight(args.host, args.port):
        return 1

    # Step 3: start the API.
    import uvicorn

    shown_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"\nStarting backend ->  http://{shown_host}:{args.port}   "
          f"(health: /health   docs: /docs)   Press Ctrl+C to stop.\n")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(BACKEND / "app")] if args.reload else None,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
