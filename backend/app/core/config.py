"""Application settings, loaded from environment variables / a .env file (see .env.example)."""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ folder. Relative paths in settings are resolved from here, so the app
# works no matter which directory uvicorn / pytest is started from.
BASE_DIR = Path(__file__).resolve().parents[2]
# The project folder that contains backend/ (in this project: 'Final Project'). The notebook lives there
# and, by default, writes its vector store to <PROJECT_ROOT>/data/vector_store.
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    """Every value can be overridden with an environment variable of the same name (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- API ---
    app_name: str = "Helios RAG Assistant API"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:8501,http://localhost:7860"   # comma-separated
    max_question_chars: int = 1000

    # --- Vector store exported by the notebook (section 2.7) ---
    # Leave empty (recommended): the backend auto-detects the store in
    #   1) backend/data/vector_store        (layout required by the assignment / Docker)
    #   2) <project>/data/vector_store      (where the notebook writes it by default)
    # and uses the most recently built one. Set VECTOR_STORE_DIR only to force a specific folder.
    vector_store_dir: Optional[str] = None

    # --- Ollama (local LLM) ---
    # 127.0.0.1 (not 'localhost'): on Windows 'localhost' can resolve to IPv6, where Ollama does not listen.
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_timeout: float = 120.0
    temperature: float = 0.0
    num_ctx: int = 4096

    # --- Optional overrides. When left empty, the values saved by the notebook in
    #     <vector_store_dir>/config.json are used, so backend and notebook stay identical. ---
    ollama_model: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    min_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @property
    def vector_store_candidates(self) -> List[Path]:
        """Folders searched for the vector store, in priority order."""
        if self.vector_store_dir:
            path = Path(self.vector_store_dir)
            return [path if path.is_absolute() else BASE_DIR / path]
        return [BASE_DIR / "data" / "vector_store", PROJECT_ROOT / "data" / "vector_store"]

    @staticmethod
    def is_valid_store(path: Path) -> bool:
        """A store exported by the notebook has a config.json and a chroma/ folder."""
        return (path / "config.json").is_file() and (path / "chroma").is_dir()

    def resolve_vector_store(self) -> Optional[Path]:
        """Return the folder to load, or None if no valid store exists.
        If several valid stores exist, the most recently built one wins (avoids serving a stale copy)."""
        valid = [p for p in self.vector_store_candidates if self.is_valid_store(p)]
        if not valid:
            return None
        return max(valid, key=lambda p: (p / "config.json").stat().st_mtime)

    @property
    def vector_store_path(self) -> Path:
        """The resolved store folder (or the first candidate, for error messages, if none exists)."""
        return self.resolve_vector_store() or self.vector_store_candidates[0]

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once."""
    return Settings()


def resolve(override: Any, store_config: Dict[str, Any], key: str, default: Any) -> Any:
    """Pick a value: explicit setting > value stored by the notebook > built-in default."""
    if override is not None:
        return override
    return store_config.get(key, default)
