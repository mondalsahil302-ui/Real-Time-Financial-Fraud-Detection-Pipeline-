"""Load ML models once in each reusable Spark Python worker process.

Both the Isolation Forest and XGBoost models are loaded lazily per-worker
from local disk. No Spark broadcast is used for model objects – the models
are never serialized into task closures or transmitted over the network.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import joblib
import xgboost as xgb

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Isolation Forest worker-local state
# ---------------------------------------------------------------------------
_IF_MODEL: Any | None = None
_IF_MODEL_PATH: Path | None = None
_IF_LOCK = threading.Lock()


def load_isolation_forest(model_path: str, expected_features: int = 33) -> Any:
    """Load the Isolation Forest once for this Python worker process.

    The model is cached in the module-level ``_IF_MODEL`` global so that
    subsequent micro-batches in the same worker process skip disk I/O.
    """
    global _IF_MODEL, _IF_MODEL_PATH

    path = Path(model_path).resolve(strict=True)
    if _IF_MODEL is not None and _IF_MODEL_PATH == path:
        return _IF_MODEL

    with _IF_LOCK:
        # Double-checked locking
        if _IF_MODEL is not None and _IF_MODEL_PATH == path:
            return _IF_MODEL

        LOGGER.info(
            "[worker pid=%d] Loading Isolation Forest from %s",
            os.getpid(),
            path,
        )
        model = joblib.load(path)
        feature_count = getattr(model, "n_features_in_", None)
        if feature_count is not None and int(feature_count) != expected_features:
            raise ValueError(
                "The worker-loaded Isolation Forest does not accept "
                f"{expected_features} features. n_features_in_={feature_count}"
            )

        _IF_MODEL = model
        _IF_MODEL_PATH = path
        LOGGER.info(
            "[worker pid=%d] Isolation Forest loaded (n_features_in_=%s)",
            os.getpid(),
            feature_count,
        )
        return model


# ---------------------------------------------------------------------------
# XGBoost worker-local state
# ---------------------------------------------------------------------------
_XGB_MODEL: Any | None = None
_XGB_MODEL_PATH: Path | None = None
_XGB_LOCK = threading.Lock()


def load_xgboost(model_path: str) -> Any:
    """Load the XGBoost second-stage classifier once for this Python worker process.

    The model is cached in the module-level ``_XGB_MODEL`` global so that
    subsequent micro-batches in the same worker process skip disk I/O.
    """
    global _XGB_MODEL, _XGB_MODEL_PATH

    path = Path(model_path).resolve(strict=True)
    if _XGB_MODEL is not None and _XGB_MODEL_PATH == path:
        return _XGB_MODEL

    with _XGB_LOCK:
        # Double-checked locking
        if _XGB_MODEL is not None and _XGB_MODEL_PATH == path:
            return _XGB_MODEL

        LOGGER.info(
            "[worker pid=%d] Loading XGBoost model from %s",
            os.getpid(),
            path,
        )
        model = xgb.XGBClassifier()
        model.load_model(str(path))

        _XGB_MODEL = model
        _XGB_MODEL_PATH = path
        LOGGER.info(
            "[worker pid=%d] XGBoost model loaded",
            os.getpid(),
        )
        return model
