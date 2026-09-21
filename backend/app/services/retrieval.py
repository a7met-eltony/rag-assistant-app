"""Retrieval: load the vector store exported by the notebook and fetch the most relevant chunks."""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import Settings, resolve

logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    """The vector store is missing, empty or inconsistent with its config."""


def load_embedder(model_name: str) -> Any:
    """Load the sentence-transformers model, preferring the local Hugging Face cache.

    The notebook already downloaded the model, so this starts faster and also works with NO internet
    (useful for a live demo). If it is not cached yet, it is downloaded normally.
    """
    from sentence_transformers import SentenceTransformer  # heavy import kept lazy

    try:
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        logger.info("Embedding model '%s' is not in the local cache; downloading it once...", model_name)
        return SentenceTransformer(model_name)


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk."""

    rank: int
    chunk_id: str
    text: str
    source: str
    page: int            # 0 means "not applicable" (plain text / markdown files)
    chunk_index: int
    similarity: float    # cosine similarity in [-1, 1]; ~1 means "very relevant"


class RetrievalService:
    """Holds the Chroma collection and the embedding model. Built ONCE at startup (see main.py)."""

    def __init__(
        self,
        collection: Any,
        embedder: Any,
        store_config: Dict[str, Any],
        top_k: int,
        store_dir: Optional[Path] = None,
    ):
        self.collection = collection
        self.embedder = embedder
        self.store_config = store_config
        self.top_k = top_k
        self.store_dir = store_dir       # shown by /health so you can see WHICH store is being served

    # ------------------------------------------------------------------ properties used by /health
    @property
    def num_chunks(self) -> int:
        return int(self.collection.count())

    @property
    def embedding_model(self) -> str:
        return str(self.store_config.get("embedding_model", "unknown"))

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, settings: Settings) -> "RetrievalService":
        """Open the persisted store. Raises VectorStoreError with a clear message if anything is wrong."""
        store_dir = settings.resolve_vector_store()
        if store_dir is None:
            searched = "; ".join(str(p) for p in settings.vector_store_candidates)
            raise VectorStoreError(
                f"Vector store not found. Looked in: {searched}. Run the notebook (section 2.7) so it exports "
                f"'config.json' and 'chroma/' to one of these folders, or set VECTOR_STORE_DIR."
            )
        config_file = store_dir / "config.json"
        chroma_dir = store_dir / "chroma"

        store_config = json.loads(config_file.read_text(encoding="utf-8"))

        # Heavy imports are done here (not at module import time) so unit tests stay fast.
        import chromadb

        try:
            client = chromadb.PersistentClient(path=str(chroma_dir))
            collection = client.get_collection(store_config["collection_name"])
        except Exception as exc:  # chromadb raises different exception types across versions
            raise VectorStoreError(f"Could not open Chroma collection: {exc}") from exc

        count = collection.count()
        if count == 0:
            raise VectorStoreError("The Chroma collection is empty. Rebuild the vector store in the notebook.")
        expected = store_config.get("num_chunks")
        if expected is not None and count != expected:
            logger.warning("Chunk count (%d) differs from config.json (%d).", count, expected)

        # The embedding model MUST be the one used to build the index, so it comes from config.json.
        embedder = load_embedder(store_config["embedding_model"])
        expected_dim = store_config.get("embedding_dimension")
        actual_dim = len(embedder.encode(["dimension check"], normalize_embeddings=True)[0])
        if expected_dim is not None and actual_dim != expected_dim:
            raise VectorStoreError(
                f"Embedding dimension mismatch: index has {expected_dim}, model produces {actual_dim}."
            )

        top_k = int(resolve(settings.top_k, store_config, "top_k", 5))
        logger.info("Vector store loaded from %s: %d chunks | model=%s | top_k=%d",
                    store_dir, count, store_config["embedding_model"], top_k)
        return cls(collection, embedder, store_config, top_k, store_dir)

    # ------------------------------------------------------------------ retrieval
    def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Hit]:
        """Embed the question and return the nearest chunks, best first."""
        k = top_k or self.top_k
        query_embedding = self.embedder.encode([question], normalize_embeddings=True, convert_to_numpy=True)
        result = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        hits: List[Hit] = []
        rows = zip(result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0])
        for rank, (chunk_id, text, meta, distance) in enumerate(rows, start=1):
            hits.append(
                Hit(
                    rank=rank,
                    chunk_id=chunk_id,
                    text=text,
                    source=meta["source"],
                    page=int(meta.get("page", 0)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    similarity=float(1.0 - distance),   # Chroma cosine distance = 1 - cosine similarity
                )
            )
        return hits
