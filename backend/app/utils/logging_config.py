"""Central logging setup."""
import logging

NOISY_LOGGERS = ("httpx", "httpcore", "huggingface_hub", "sentence_transformers", "urllib3", "chromadb")


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger once and silence chatty third-party libraries."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        force=True,   # replace handlers uvicorn/pytest may have installed, so the format is consistent
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
