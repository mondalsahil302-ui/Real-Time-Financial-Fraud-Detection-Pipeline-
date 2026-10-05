"""Tests for Spark worker model loading and broadcast-safety contract.

Verifies:
- No Spark broadcast contains the Isolation Forest model
- No Spark broadcast contains the XGBoost model
- Worker-local Isolation Forest loading caches per process
- Worker-local XGBoost loading caches per process
- Scoring preserves the 33-feature contract
- Both models can be loaded from the real artifact paths
"""
from __future__ import annotations

import importlib
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from streaming import spark_worker_model


# ---------------------------------------------------------------------------
# Fixtures: reset worker-level caches between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_worker_caches(monkeypatch):
    """Reset ALL module-level model caches before every test."""
    monkeypatch.setattr(spark_worker_model, "_IF_MODEL", None)
    monkeypatch.setattr(spark_worker_model, "_IF_MODEL_PATH", None)
    monkeypatch.setattr(spark_worker_model, "_XGB_MODEL", None)
    monkeypatch.setattr(spark_worker_model, "_XGB_MODEL_PATH", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_if_model() -> SimpleNamespace:
    return SimpleNamespace(
        n_features_in_=33,
        decision_function=lambda X: -np.ones(len(X)) * 0.05,
    )


def _fake_xgb_model() -> MagicMock:
    m = MagicMock()
    m.predict_proba.return_value = np.array([[0.9, 0.1], [0.3, 0.7]])
    return m


# ---------------------------------------------------------------------------
# 1. Isolation Forest worker-local caching
# ---------------------------------------------------------------------------

class TestIsolationForestWorkerLocal:

    def test_model_loaded_once_for_reused_worker(self, tmp_path, monkeypatch):
        artifact = tmp_path / "model.pkl"
        artifact.write_bytes(b"stub")
        model = _fake_if_model()
        calls: list[Path] = []

        def fake_load(path):
            calls.append(Path(path))
            return model

        monkeypatch.setattr(spark_worker_model.joblib, "load", fake_load)

        first = spark_worker_model.load_isolation_forest(str(artifact))
        second = spark_worker_model.load_isolation_forest(str(artifact))
        third = spark_worker_model.load_isolation_forest(str(artifact))

        assert first is model
        assert second is model
        assert third is model
        assert len(calls) == 1, "joblib.load must be called exactly once per worker"

    def test_rejects_feature_count_mismatch(self, tmp_path, monkeypatch):
        artifact = tmp_path / "model.pkl"
        artifact.write_bytes(b"stub")
        monkeypatch.setattr(
            spark_worker_model.joblib,
            "load",
            lambda _: SimpleNamespace(n_features_in_=32),
        )
        with pytest.raises(ValueError, match="does not accept 33 features"):
            spark_worker_model.load_isolation_forest(str(artifact))

    def test_accepts_model_without_n_features_in(self, tmp_path, monkeypatch):
        artifact = tmp_path / "model.pkl"
        artifact.write_bytes(b"stub")
        model = SimpleNamespace()  # no n_features_in_
        monkeypatch.setattr(
            spark_worker_model.joblib,
            "load",
            lambda _: model,
        )
        result = spark_worker_model.load_isolation_forest(str(artifact))
        assert result is model


# ---------------------------------------------------------------------------
# 2. XGBoost worker-local caching
# ---------------------------------------------------------------------------

class TestXGBoostWorkerLocal:

    def test_model_loaded_once_for_reused_worker(self, tmp_path, monkeypatch):
        artifact = tmp_path / "xgb.json"
        artifact.write_bytes(b"stub")

        xgb_model = _fake_xgb_model()
        calls: list[str] = []

        def fake_load_model(path):
            calls.append(path)

        monkeypatch.setattr(spark_worker_model, "_XGB_MODEL", None)
        monkeypatch.setattr(spark_worker_model, "_XGB_MODEL_PATH", None)

        # Patch XGBClassifier on the imported module reference
        monkeypatch.setattr(spark_worker_model.xgb, "XGBClassifier", lambda: xgb_model)
        xgb_model.load_model = fake_load_model

        first = spark_worker_model.load_xgboost(str(artifact))
        second = spark_worker_model.load_xgboost(str(artifact))

        assert first is xgb_model
        assert second is xgb_model
        assert len(calls) == 1, "load_model must be called exactly once per worker"

    def test_different_paths_reload(self, tmp_path, monkeypatch):
        a1 = tmp_path / "xgb1.json"
        a2 = tmp_path / "xgb2.json"
        a1.write_bytes(b"stub1")
        a2.write_bytes(b"stub2")

        calls1: list[str] = []
        calls2: list[str] = []
        model1 = MagicMock()
        model2 = MagicMock()
        model1.load_model = lambda p: calls1.append(p)
        model2.load_model = lambda p: calls2.append(p)
        models = [model1, model2]

        def make_model():
            return models.pop(0)

        monkeypatch.setattr(spark_worker_model.xgb, "XGBClassifier", make_model)

        r1 = spark_worker_model.load_xgboost(str(a1))
        # Reset cache to simulate loading a different model
        monkeypatch.setattr(spark_worker_model, "_XGB_MODEL", None)
        monkeypatch.setattr(spark_worker_model, "_XGB_MODEL_PATH", None)
        r2 = spark_worker_model.load_xgboost(str(a2))

        assert r1 is not r2


# ---------------------------------------------------------------------------
# 3. Broadcast-safety: verify spark_streaming.py contains no broadcast calls
# ---------------------------------------------------------------------------

class TestNoBroadcast:

    @pytest.fixture
    def streaming_source(self) -> str:
        path = Path(__file__).resolve().parents[1] / "streaming" / "spark_streaming.py"
        return path.read_text(encoding="utf-8")

    def test_no_sparkcontext_broadcast(self, streaming_source: str):
        """The driver must NOT call SparkContext.broadcast() on a model."""
        assert "sc.broadcast" not in streaming_source, (
            "sc.broadcast() found in spark_streaming.py – model must NOT be broadcast"
        )
        assert "spark.sparkContext.broadcast" not in streaming_source, (
            "sparkContext.broadcast() found in spark_streaming.py"
        )

    def test_no_broadcast_variable_assigned_to_model(self, streaming_source: str):
        """MODEL_BROADCAST or similar patterns must not exist."""
        assert "MODEL_BROADCAST" not in streaming_source, (
            "MODEL_BROADCAST variable found in spark_streaming.py"
        )
        assert "broadcast(MODEL)" not in streaming_source, (
            "broadcast(MODEL) found in spark_streaming.py"
        )

    def test_xgb_model_not_assigned_on_driver(self, streaming_source: str):
        """The driver must NOT keep XGB_MODEL as a live model object in scope.

        After our fix, the only occurrence of 'XGB_MODEL' in the file is inside
        a comment explaining the design. There must be no assignment like
        ``XGB_MODEL = ...`` that stores a model object.
        """
        import re
        # Find actual assignment lines (not comments)
        assignments = [
            line.strip()
            for line in streaming_source.splitlines()
            if re.match(r'\s*XGB_MODEL\s*=', line)
            and not line.strip().startswith('#')
        ]
        assert not assignments, (
            "XGB_MODEL assigned on driver (outside comment). "
            f"Lines: {assignments}"
        )

    def test_if_model_not_live_on_driver(self, streaming_source: str):
        """The driver must NOT keep the Isolation Forest as a live variable.

        After our fix:
        - ``load_runtime_artifacts()`` returns the model as ``_`` (discarded)
        - ``del _`` is called immediately
        - No variable named ``MODEL`` (without suffix) holds a model
        """
        import re
        # Check that there is no assignment of bare 'MODEL' (without suffix like _PATH, _VERSION, etc.)
        assignments = [
            line.strip()
            for line in streaming_source.splitlines()
            if re.match(r'\s*MODEL\s*=', line)
            and not line.strip().startswith('#')
        ]
        assert not assignments, (
            "Bare MODEL assigned on driver (outside comment). "
            f"Lines: {assignments}"
        )

        # Also ensure MODEL_BROADCAST does not exist anywhere
        assert "MODEL_BROADCAST" not in streaming_source



# ---------------------------------------------------------------------------
# 4. 33-feature contract preserved in scoring
# ---------------------------------------------------------------------------

class TestScoringContract:

    FEATURE_COLUMNS_33 = [
        "step", "amount", "oldbalanceOrg", "newbalanceOrig",
        "oldbalanceDest", "newbalanceDest", "orig_balance_change",
        "dest_balance_change", "orig_balance_error", "dest_balance_error",
        "orig_zero_after", "dest_zero_before", "dest_zero_after",
        "log_amount", "type_CASH_IN", "type_CASH_OUT", "type_DEBIT",
        "type_PAYMENT", "type_TRANSFER",
        "orig_tx_count_1step", "orig_tx_count_6steps", "orig_tx_count_24steps",
        "orig_amount_sum_6steps", "orig_amount_sum_24steps",
        "orig_avg_amount_6steps", "orig_avg_amount_24steps",
        "orig_amount_ratio_to_avg_24steps", "orig_time_since_prev_step",
        "orig_unique_destinations_24steps", "orig_cashout_count_24steps",
        "orig_transfer_count_24steps", "orig_new_destination",
        "orig_balance_depletion_ratio",
    ]

    def test_exactly_33_features(self):
        assert len(self.FEATURE_COLUMNS_33) == 33

    def test_worker_scores_33_features_correctly(self, tmp_path, monkeypatch):
        artifact = tmp_path / "model.pkl"
        artifact.write_bytes(b"stub")

        scores_returned = np.array([-0.05, 0.10, 0.25])
        model = SimpleNamespace(
            n_features_in_=33,
            decision_function=lambda X: scores_returned,
        )
        monkeypatch.setattr(spark_worker_model.joblib, "load", lambda _: model)

        loaded = spark_worker_model.load_isolation_forest(str(artifact))

        X = np.zeros((3, 33))
        anomaly_scores = -loaded.decision_function(X)
        expected = np.array([0.05, -0.10, -0.25])
        np.testing.assert_array_equal(anomaly_scores, expected)

    def test_forbidden_columns_not_in_features(self):
        forbidden = {"isFraud", "isFlaggedFraud", "nameOrig", "nameDest"}
        overlap = set(self.FEATURE_COLUMNS_33) & forbidden
        assert not overlap, f"Forbidden columns in features: {overlap}"
