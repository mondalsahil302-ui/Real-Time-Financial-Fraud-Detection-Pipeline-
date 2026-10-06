from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from streaming import spark_worker_model


@pytest.fixture(autouse=True)
def reset_worker_model(monkeypatch):
    monkeypatch.setattr(spark_worker_model, "_MODEL", None)
    monkeypatch.setattr(spark_worker_model, "_MODEL_PATH", None)


def test_model_is_loaded_once_for_reused_worker(tmp_path, monkeypatch):
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"test artifact")
    model = SimpleNamespace(n_features_in_=33)
    calls = []

    def load(path):
        calls.append(Path(path))
        return model

    monkeypatch.setattr(spark_worker_model.joblib, "load", load)

    first = spark_worker_model.load_isolation_forest(str(artifact))
    second = spark_worker_model.load_isolation_forest(str(artifact))

    assert first is model
    assert second is model
    assert calls == [artifact.resolve()]


def test_worker_model_rejects_feature_contract_mismatch(tmp_path, monkeypatch):
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"test artifact")
    monkeypatch.setattr(
        spark_worker_model.joblib,
        "load",
        lambda _: SimpleNamespace(n_features_in_=32),
    )

    with pytest.raises(ValueError, match="does not accept 33 features"):
        spark_worker_model.load_isolation_forest(str(artifact))
