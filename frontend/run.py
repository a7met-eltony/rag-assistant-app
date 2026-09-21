#!/usr/bin/env python3
"""Start the Streamlit frontend with one command.

    python run.py                 # from the frontend/ folder; opens http://127.0.0.1:8501 in your browser
    python run.py --port 8502     # another port
    python run.py --test          # run the frontend tests
    python run.py --venv          # always use an isolated .venv (created and filled automatically)
    python run.py --no-venv       # never create a .venv: use this Python (packages must already be installed)
    python run.py --no-browser    # do not open the browser
    python run.py --skip-install  # with --venv: do not run pip

By default it uses the Python you started it with if streamlit, requests and python-dotenv are already
installed. Otherwise it creates frontend/.venv and installs requirements.txt there (first time: a few minutes).
Before starting it checks whether the backend is reachable and ready, and tells you what to fix if not.
It only uses the Python standard library, so it works before any package is installed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

FRONTEND = Path(__file__).resolve().parent
VENV_DIR = FRONTEND / ".venv"
REQUIREMENTS = FRONTEND / "requirements.txt"

RUN_MODULES = ["streamlit", "requests", "dotenv"]          # 'dotenv' is the import name of python-dotenv
TEST_MODULES = RUN_MODULES + ["pytest"]


# ----------------------------------------------------------------------------- settings
def read_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip().upper()] = value.strip().strip('"').strip("'")
    return values


def missing_modules(modules: List[str]) -> List[str]:
    return [m for m in modules if importlib.util.find_spec(m) is None]


# ----------------------------------------------------------------------------- virtual environment
def venv_python(venv_dir: Path = VENV_DIR) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv(skip_install: bool = False, venv_dir: Path = VENV_DIR, requirements: Path = REQUIREMENTS) -> Path:
    """Create the virtual environment if needed and (re)install requirements.txt when it changed."""
    python = venv_python(venv_dir)
    if not python.exists():
        print(f"[setup] Creating virtual environment in {venv_dir} ...")
        venv.create(venv_dir, with_pip=True)
    if skip_install:
        return python

    stamp = venv_dir / ".requirements.sha256"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip() != digest:
        print("[setup] Installing packages (the first time takes a few minutes) ...")
        if subprocess.run([str(python), "-m", "pip", "install", "-q", "-r", str(requirements)]).returncode != 0:
            sys.exit("\n[error] Installing the packages failed. Read the messages above "
                     "(internet connection? disk space?), then run the script again.")
        stamp.write_text(digest)
    return python


# ----------------------------------------------------------------------------- pre-flight (warnings only)
def backend_health(base_url: str) -> Optional[dict]:
    """The backend's /health JSON, or None if it cannot be reached."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=3) as response:
            return json.load(response)
    except Exception:
        return None


def preflight(dotenv: Dict[str, str]) -> None:
    base_url = os.environ.get("API_BASE_URL") or dotenv.get("API_BASE_URL", "")
    print("=== Preflight ===")
    if not base_url:
        print("[WARN] API_BASE_URL is not set. Add it to frontend/.env (example: API_BASE_URL=http://127.0.0.1:8000)")
        return
    health = backend_health(base_url)
    if health is None:
        print(f"[WARN] Backend not reachable at {base_url}")
        print("       Start it first, in another terminal:   cd ..\\backend   then   python run.py --no-venv")
        print("       (the app still opens and will show a friendly message until the backend is up)")
    elif health.get("status") == "ok":
        print(f"[ OK ] Backend ready at {base_url}  ({health.get('num_chunks')} passages, model {health.get('ollama_model')})")
    else:
        print(f"[WARN] Backend is running at {base_url} but not ready: {health.get('detail') or 'see /health'}")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def open_browser_when_ready(host: str, port: int, timeout: float = 60) -> None:
    """Wait until Streamlit accepts connections, then open the page (runs in a background thread)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_in_use(host, port):
            webbrowser.open(f"http://{host}:{port}")
            return
        time.sleep(0.5)


# ----------------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="Start the RAG frontend (Streamlit).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--test", action="store_true", help="run the tests instead of the app")
    parser.add_argument("--venv", action="store_true", help="always use an isolated .venv")
    parser.add_argument("--no-venv", action="store_true", help="use the current Python, never create a .venv")
    parser.add_argument("--skip-install", action="store_true", help="with --venv: do not run pip")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        sys.exit(f"[error] Python 3.10 or newer is required (you have {sys.version.split()[0]}).")
    os.chdir(FRONTEND)

    missing = missing_modules(TEST_MODULES if args.test else RUN_MODULES)
    if args.venv and args.no_venv:
        sys.exit("[error] Use either --venv or --no-venv, not both.")
    if args.no_venv and missing:
        sys.exit(f"[error] These packages are missing in this Python: {', '.join(missing)}\n"
                 f"        Install them with:  pip install -r requirements.txt   (or drop --no-venv to let run.py create .venv)")

    print("Frontend launcher")
    print(f"  Python : {sys.version.split()[0]}")
    if args.venv or missing:
        reason = "--venv" if args.venv else f"missing here: {', '.join(missing)}"
        print(f"  Mode   : isolated .venv ({reason})")
        python = str(ensure_venv(args.skip_install))
    else:
        print("  Mode   : current Python (all required packages found)")
        python = sys.executable

    if args.test:
        print()
        return subprocess.run([python, "-m", "pytest", "-q"], cwd=FRONTEND).returncode

    print()
    preflight(read_dotenv(FRONTEND / ".env"))

    if port_in_use(args.host, args.port):
        print(f"[FAIL] Port {args.port} is already in use (is the frontend already running?). "
              f"Close it, or use:  python run.py --port {args.port + 1}")
        return 1
    print(f"[ OK ] Port {args.port} is free")

    print(f"\nStarting frontend ->  http://{args.host}:{args.port}   Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(args.host, args.port), daemon=True).start()

    command = [
        python, "-m", "streamlit", "run", "app.py",
        "--server.address", args.host, "--server.port", str(args.port),
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ]
    process = subprocess.Popen(command, cwd=FRONTEND)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
