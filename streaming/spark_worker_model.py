"""Load the Isolation Forest once in each reusable Spark Python worker."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import joblib

LOGGER = logging.getLogger(__name__)
_MODEL: Any | None = None
_MODEL_PATH: Path | None = None
_MODEL_LOCK = threading.Lock()


def load_isolation_forest(model_path: str, expected_features: int = 33) -> Any:
    """Load the unchanged model artifact once for this Python worker process."""
    global _MODEL, _MODEL_PATH

    path = Path(model_path).resolve(strict=True)
    if _MODEL is not None and _MODEL_PATH == path:
        return _MODEL

    with _MODEL_LOCK:
        if _MODEL is not None and _MODEL_PATH == path:
            return _MODEL

        model = joblib.load(path)
        feature_count = getattr(model, "n_features_in_", None)
        if feature_count is not None and int(feature_count) != expected_features:
            raise ValueError(
                "The worker-loaded Isolation Forest does not accept "
                f"{expected_features} features. n_features_in_={feature_count}"
            )

        _MODEL = model
        _MODEL_PATH = path
        LOGGER.info(
            "Loaded worker-local Isolation Forest model (pid=%d)",
            os.getpid(),
        )
        return model
