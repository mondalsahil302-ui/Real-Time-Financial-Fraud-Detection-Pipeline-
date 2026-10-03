"""Local sentence-transformer embeddings; no API credentials are used."""
from __future__ import annotations

import logging
import numpy as np

LOGGER = logging.getLogger(__name__)


class LocalEmbedder:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
            try:
                self.model = SentenceTransformer(model_name, local_files_only=True)
            except Exception:
                LOGGER.info("Embedding model is not cached locally; downloading it once for local use")
                self.model = SentenceTransformer(model_name)
            dimension_getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
            self.dimension = int(dimension_getter())
            if self.dimension <= 0:
                raise ValueError("embedding model returned an invalid dimension")
        except Exception as exc:
            raise RuntimeError(f"Could not load local embedding model {model_name!r}: {exc}") from exc
        LOGGER.info("Loaded embedding model %s (%d dimensions)", model_name, self.dimension)

    def encode(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim != 2 or array.shape != (len(texts), self.dimension):
            raise ValueError(f"Unexpected embedding shape: {array.shape}")
        return array.tolist()
