FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# CPU-only PyTorch keeps the image ~1.5 GB smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY data ./data

# Download the embedding model (named in config.json) at build time, so the container starts fast
# and does not depend on Hugging Face at runtime.
RUN python -c "import json; from sentence_transformers import SentenceTransformer; SentenceTransformer(json.load(open('data/vector_store/config.json'))['embedding_model'])"

# Ollama runs on the HOST machine, not inside the container.
ENV OLLAMA_HOST=http://host.docker.internal:11434 \
    VECTOR_STORE_DIR=data/vector_store \
    CORS_ORIGINS=http://localhost:8501,http://localhost:7860

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
