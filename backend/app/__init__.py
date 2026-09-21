"""Helios RAG Assistant - FastAPI backend."""
import os

# These must be set BEFORE chromadb / sentence-transformers are imported anywhere in the app,
# which is why they live in the package's __init__ (it always runs first).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")       # no Chroma telemetry calls
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")     # avoid tokenizer fork warnings
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")   # plain logs, no progress-bar widgets
os.environ.setdefault("TQDM_DISABLE", "1")
